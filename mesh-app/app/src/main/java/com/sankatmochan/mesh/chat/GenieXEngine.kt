package com.sankatmochan.mesh.chat

import android.content.Context
import android.net.Uri
import android.util.Log
import com.sankatmochan.mesh.BuildConfig
import com.geniex.sdk.GenieXSdk
import com.geniex.sdk.LlmWrapper
import com.geniex.sdk.ModelManagerWrapper
import com.geniex.sdk.bean.ChatMessage
import com.geniex.sdk.bean.ComputeUnitValue
import com.geniex.sdk.bean.GenerationConfig
import com.geniex.sdk.bean.HubSource
import com.geniex.sdk.bean.LlmCreateInput
import com.geniex.sdk.bean.LlmStreamResult
import com.geniex.sdk.bean.ModelConfig
import com.geniex.sdk.bean.ModelPullInput
import com.geniex.sdk.bean.ModelType
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.File
import java.io.IOException
import java.util.Locale
import kotlin.coroutines.resume

/**
 * All Qualcomm GenieX on-device-LLM calls live behind this one class, so the rest of the app
 * never imports `com.geniex.sdk.*` and there is a single place to review the AI runtime
 * (CLAUDE.md #5/#6). The SDK runs small GGUF chat models through its llama.cpp runtime on the
 * Snapdragon NPU/GPU/CPU, fully offline once the weights are on the phone.
 *
 * The GenieX call sequence is taken directly from Qualcomm's BSD-3-Clause reference app
 * (CLAUDE.md #3/#4):
 *   https://github.com/qualcomm/ai-hub-apps/blob/main/geniex_chat_android/src/main/java/com/geniex/demo/MainActivity.kt
 *   init → ModelManagerWrapper.pullFlow (download) → getPaths → LlmWrapper.build (load) →
 *   applyChatTemplate → generateStreamFlow (stream tokens).
 *
 * Every method is safe to call from a coroutine on any dispatcher - the heavy work is moved
 * onto [Dispatchers.IO] internally. Instances are cheap; hold one per assistant session.
 */
class GenieXEngine(context: Context) {

    private val appContext = context.applicationContext

    /**
     * Where side-loaded models live. App-scoped external storage needs no runtime permission
     * and is reachable over adb - you can `adb push model.gguf` into
     * `Android/data/<pkg>/files/models/` and it shows up in the picker (plug-and-play).
     */
    val localModelsDir: File = File(appContext.getExternalFilesDir(null), "models")

    /** Guards one-time SDK init and the single native LLM handle. */
    private val lock = Mutex()

    @Volatile
    private var initialized = false

    /** The loaded model handle, or null when nothing is loaded. */
    private var wrapper: LlmWrapper? = null

    /** Conversation so far, replayed to [LlmWrapper.applyChatTemplate] every turn. Index 0 is
     *  always the system prompt. Only ever touched under [lock] or on the single generate
     *  coroutine, which the ViewModel serialises. */
    private val history = ArrayList<ChatMessage>()

    val isLoaded: Boolean get() = wrapper != null

    // ── Init ──────────────────────────────────────────────────────────────────

    sealed interface InitResult {
        data object Ready : InitResult
        /** The device or build can't run GenieX (e.g. an emulator, or a non-Snapdragon part). */
        data class Unsupported(val reason: String) : InitResult
    }

    /** Bring the SDK up once. Idempotent - repeated calls after a success return [Ready]. */
    suspend fun initialize(): InitResult = lock.withLock {
        if (initialized) return@withLock InitResult.Ready
        val ok = runCatching { awaitInit() }.getOrElse { e ->
            Log.e(TAG, "GenieX init threw", e)
            false
        }
        if (ok) {
            initialized = true
            InitResult.Ready
        } else {
            // Generic, user-safe message - the real reason is only in Logcat (CLAUDE.md #10).
            InitResult.Unsupported("On-device AI is not available on this device.")
        }
    }

    private suspend fun awaitInit(): Boolean = suspendCancellableCoroutine { cont ->
        GenieXSdk.getInstance().init(appContext, object : GenieXSdk.InitCallback {
            override fun onSuccess() {
                if (cont.isActive) cont.resume(true)
            }

            override fun onFailure(reason: String) {
                Log.e(TAG, "GenieX init failed: $reason")
                if (cont.isActive) cont.resume(false)
            }
        })
    }

    // ── Download ──────────────────────────────────────────────────────────────

    /** True when the model is ready to load - a local file on disk, or a cached hub pull. */
    suspend fun isDownloaded(model: AssistantModel): Boolean = withContext(Dispatchers.IO) {
        if (model.isLocal) return@withContext File(model.localPath!!).exists()
        runCatching { ModelManagerWrapper.getPaths(model.modelName) != null }.getOrDefault(false)
    }

    /**
     * Download [model]'s weights, emitting whole-percent progress (0..100). Resumable: a
     * cancelled collection leaves partial files on disk for the next call to continue. Throws
     * [IOException] on a hub error so the caller can show a retry.
     *
     * Gated models (e.g. Gemma) carry the Hugging Face token from BuildConfig; it is only sent
     * to Hugging Face for the pull and never logged.
     */
    fun downloadFlow(model: AssistantModel): Flow<Int> = flow {
        // Local models are already on disk - nothing to pull.
        if (model.isLocal) {
            emit(100)
            return@flow
        }
        val input = ModelPullInput(
            model_name = model.modelName,
            precision = model.quant,
            hub = HubSource.HUGGINGFACE,
            hf_token = if (model.gated) BuildConfig.HF_TOKEN else "",
            chipset = null,       // GGUF/HuggingFace pulls are chipset-agnostic.
            display_name = null,
            model_type = ModelType.LLM,
        )
        emit(0)
        ModelManagerWrapper.pullFlow(input).collect { event ->
            when (event) {
                is ModelManagerWrapper.PullEvent.Progress -> {
                    val total = event.files.sumOf { if (it.total_bytes > 0) it.total_bytes else 0L }
                    val done = event.files.sumOf { it.downloaded_bytes }
                    val pct = if (total > 0) ((done * 100) / total).toInt() else 0
                    emit(pct.coerceIn(0, 99))
                }

                is ModelManagerWrapper.PullEvent.Completed -> emit(100)

                is ModelManagerWrapper.PullEvent.Error -> {
                    Log.e(TAG, "model pull failed rc=${event.code}: ${event.message}")
                    throw IOException("model-download-failed")
                }
            }
        }
    }.flowOn(Dispatchers.IO)

    // ── Load ──────────────────────────────────────────────────────────────────

    sealed interface LoadResult {
        data object Ok : LoadResult
        data class Failed(val message: String) : LoadResult
    }

    /**
     * Load a downloaded [model] into a native LLM handle and start a fresh conversation.
     *
     * @param onNpu run on the Snapdragon NPU (all layers offloaded); false keeps it on the CPU
     *   as a universally-available fallback. For llama.cpp the layer offload count is what
     *   actually picks the compute unit, so CPU mode just offloads zero layers.
     */
    suspend fun load(model: AssistantModel, onNpu: Boolean): LoadResult = lock.withLock {
        withContext(Dispatchers.IO) {
            // Resolve the on-disk model. Side-loaded files are used verbatim (llama.cpp reads
            // the tokenizer embedded in the GGUF); hub models come from the manager's cache.
            val modelPath: String
            val tokenizerPath: String
            val runtimeId: String
            val modelKey: String
            if (model.isLocal) {
                val f = File(model.localPath!!)
                if (!f.exists()) {
                    return@withContext LoadResult.Failed("That file is no longer on the phone.")
                }
                modelPath = f.absolutePath
                tokenizerPath = ""
                runtimeId = GenieXSdk.PLUGIN_ID_LLAMA_CPP
                modelKey = model.id
            } else {
                val paths = runCatching { ModelManagerWrapper.getPaths(model.modelName) }.getOrNull()
                    ?: return@withContext LoadResult.Failed("Model files are missing - download it again.")
                modelPath = paths.model_path
                    ?: return@withContext LoadResult.Failed("Model files are missing - download it again.")
                tokenizerPath = paths.tokenizer_path.orEmpty()
                // A GGUF pull writes no runtime manifest, so fall back to the llama.cpp runtime.
                runtimeId = paths.runtime_id?.ifEmpty { GenieXSdk.PLUGIN_ID_LLAMA_CPP }
                    ?: GenieXSdk.PLUGIN_ID_LLAMA_CPP
                modelKey = paths.model_name ?: model.modelName
            }

            val config = ModelConfig(
                nCtx = 2048,
                nGpuLayers = if (onNpu) 999 else 0,   // llama.cpp: full offload = NPU, 0 = CPU.
                enable_thinking = false,
            )
            val computeUnit =
                if (onNpu) ComputeUnitValue.NPU.value else ComputeUnitValue.CPU.value
            val built = LlmWrapper.builder()
                .llmCreateInput(
                    LlmCreateInput(
                        model_name = modelKey,
                        model_path = modelPath,
                        tokenizer_path = tokenizerPath,
                        config = config,
                        runtime_id = runtimeId,
                        compute_unit = computeUnit,
                    )
                )
                .build()

            built.fold(
                onSuccess = { w ->
                    wrapper?.runCatching { destroy() }   // never leak a previous handle
                    wrapper = w
                    resetHistory()
                    LoadResult.Ok
                },
                onFailure = { e ->
                    Log.e(TAG, "LLM load failed for ${model.modelName}", e)
                    LoadResult.Failed("Could not start the assistant on this device.")
                },
            )
        }
    }

    // ── Local (side-loaded) models ──────────────────────────────────────────────

    /**
     * Extensions the bundled runtime can actually load locally. Only `libgeniex_plugin_llama_cpp`
     * is wired up for side-loaded files (see [load]), and llama.cpp only reads GGUF - so this is
     * the full list, not a partial one. Formats like `.litertlm`/`.tflite`/`.task` belong to a
     * different runtime plugin (LiteRT/MediaPipe) that isn't wired into this app; adding them here
     * without a real integration would just mislabel unusable files as models (CLAUDE.md #4: don't
     * fabricate SDK behavior beyond what's actually documented/wired up).
     */
    private val SUPPORTED_LOCAL_EXTENSIONS = setOf("gguf")

    /**
     * The first 4 bytes of every valid GGUF file, per the format's public spec (MIT-licensed,
     * https://github.com/ggml-org/ggml/blob/master/docs/gguf.md). A name ending in `.gguf`
     * doesn't guarantee the bytes actually are one - an older build of this app used to
     * force-rename *any* picked file to `.gguf`, so a stale side-loaded file can still have a
     * `.gguf` name while actually being, say, a `.litertlm` bundle. Checking the extension alone
     * (CLAUDE.md #8: validate untrusted input, don't just trust its label) let those through and
     * they'd fail deep inside the native loader with an opaque "could not start" error.
     */
    private val GGUF_MAGIC = byteArrayOf(0x47, 0x47, 0x55, 0x46) // "GGUF"

    private fun File.isRealGguf(): Boolean = runCatching {
        inputStream().use { input ->
            val header = ByteArray(4)
            input.read(header) == 4 && header.contentEquals(GGUF_MAGIC)
        }
    }.getOrDefault(false)

    /** Every supported model file sitting in [localModelsDir], newest first, ready to load.
     *  Drops (and deletes) anything that merely has a `.gguf` name but isn't really one - e.g.
     *  leftovers from before extension validation existed. */
    suspend fun scanLocalModels(): List<AssistantModel> = withContext(Dispatchers.IO) {
        val files = localModelsDir.listFiles { f ->
            f.isFile && f.extension.lowercase(Locale.US) in SUPPORTED_LOCAL_EXTENSIONS
        } ?: return@withContext emptyList()
        files.filter { f ->
            f.isRealGguf() || run {
                Log.e(TAG, "dropping non-GGUF file masquerading as one: ${f.name}")
                f.delete()
                false
            }
        }.sortedByDescending { it.lastModified() }.map { it.toLocalModel() }
    }

    sealed interface ImportResult {
        data class Ok(val model: AssistantModel) : ImportResult
        /** The picked file's extension isn't one [SUPPORTED_LOCAL_EXTENSIONS] can load, or it is
         *  named `.gguf` but its contents don't start with the GGUF magic header. */
        data object UnsupportedFormat : ImportResult
        /** Right extension, but the copy itself failed (bad Uri, disk full, permission, ...). */
        data object Failed : ImportResult
    }

    /**
     * Copy a user-picked model (content:// Uri) into [localModelsDir] so the native runtime can
     * open it by path, and return it as a loadable model.
     */
    suspend fun importModel(uri: Uri, suggestedName: String): ImportResult =
        withContext(Dispatchers.IO) {
            val ext = suggestedName.substringAfterLast('.', "").lowercase(Locale.US)
            if (ext !in SUPPORTED_LOCAL_EXTENSIONS) {
                Log.e(TAG, "importModel rejected unsupported extension: $ext")
                return@withContext ImportResult.UnsupportedFormat
            }
            localModelsDir.mkdirs()
            val safe = suggestedName.substringAfterLast('/').substringAfterLast('\\')
                .replace(Regex("[^A-Za-z0-9._-]"), "_")
                .ifBlank { "model.$ext" }
            val dest = File(localModelsDir, safe)
            val ok = runCatching {
                appContext.contentResolver.openInputStream(uri)?.use { input ->
                    dest.outputStream().use { output -> input.copyTo(output) }
                } ?: error("could not open picked file")
            }.isSuccess
            if (!ok) {
                Log.e(TAG, "importModel failed for $safe")
                dest.delete()
                return@withContext ImportResult.Failed
            }
            if (!dest.isRealGguf()) {
                Log.e(TAG, "importModel rejected: $safe has a .gguf name but isn't really one")
                dest.delete()
                return@withContext ImportResult.UnsupportedFormat
            }
            ImportResult.Ok(dest.toLocalModel())
        }

    /**
     * Delete a side-loaded model file off the phone. Returns true if it is gone afterwards
     * (either we deleted it or it was already absent). The caller is responsible for first
     * unloading it if it happens to be the model currently in the native handle.
     */
    suspend fun deleteLocalModel(model: AssistantModel): Boolean = withContext(Dispatchers.IO) {
        val path = model.localPath ?: return@withContext false
        val f = File(path)
        // Refuse to follow a path that escapes the models dir - a side-loaded name is
        // untrusted (CLAUDE.md #8); we only ever delete inside our own folder.
        val insideModelsDir = runCatching {
            f.canonicalPath.startsWith(localModelsDir.canonicalPath + File.separator)
        }.getOrDefault(false)
        if (!insideModelsDir) {
            Log.e(TAG, "refusing to delete a model outside the models dir: ${f.name}")
            return@withContext false
        }
        val gone = !f.exists() || f.delete()
        if (!gone) Log.e(TAG, "could not delete local model ${f.name}")
        gone
    }

    private fun File.toLocalModel(): AssistantModel = AssistantModel(
        id = "local:$name",
        displayName = nameWithoutExtension,
        modelName = name,
        quant = "",
        approxSize = humanSize(length()),
        blurb = "On your phone · loads instantly, no download.",
        localPath = absolutePath,
    )

    private fun humanSize(bytes: Long): String {
        if (bytes <= 0) return "0 B"
        val units = arrayOf("B", "KB", "MB", "GB")
        var value = bytes.toDouble()
        var i = 0
        while (value >= 1024 && i < units.lastIndex) {
            value /= 1024; i++
        }
        return String.format(Locale.US, if (i >= 2) "%.1f %s" else "%.0f %s", value, units[i])
    }

    // ── Chat ──────────────────────────────────────────────────────────────────

    sealed interface ChatStream {
        /** One incremental piece of the answer. */
        data class Token(val text: String) : ChatStream
        /** The answer finished cleanly. */
        data object Done : ChatStream
        /** Generation failed; [message] is safe to show the user. */
        data class Failed(val message: String) : ChatStream
    }

    /**
     * Stream a reply to [userText]. Appends the turn to [history] so context carries across
     * messages; rolls the user turn back on failure so a retry isn't polluted. Collect this
     * once per send - the ViewModel guards against overlapping generations.
     */
    fun replyFlow(userText: String, replyLanguage: String? = null): Flow<ChatStream> = flow {
        val w = wrapper
        if (w == null) {
            emit(ChatStream.Failed("No model is loaded."))
            return@flow
        }

        history.add(ChatMessage(role = "user", sanitizeForSdk(userText)))

        // Send the model a sliding window - system prompt + the most recent turns - so a long
        // conversation can't overflow nCtx and kill generation mid-chat. Every content string is
        // sanitized to valid BMP text before it reaches GenieX: its applyChatTemplate JNI hands the
        // formatted prompt back via NewStringUTF (Modified UTF-8) and hard-aborts (SIGABRT) on lone
        // surrogates, 4-byte chars (emoji), or split multibyte fragments - which is what crashed the
        // app on mixed Tamil/Hindi chats.
        // The window is bounded by UTF-8 BYTES, not message count alone: Indic scripts are
        // 3 bytes/char, so "8 messages" of Hindi is ~3x the bytes of the English chats that
        // worked - and once the formatted prompt outgrows Genie's native buffer, its byte-level
        // trim splits a multibyte char and the next NewStringUTF aborts (the 0xa2/0xa4/0xbf
        // "illegal start byte" crashes). Newest-first, keep whole messages only; the latest
        // user message always survives (truncated to the budget if it alone exceeds it).
        val window = ArrayList<ChatMessage>(MAX_WINDOW_MESSAGES + 1)
        window.add(ChatMessage(role = history[0].role, sanitizeForSdk(history[0].content)))
        val tail = ArrayList<ChatMessage>(MAX_WINDOW_MESSAGES)
        var budget = MAX_WINDOW_BYTES
        for (i in history.indices.reversed()) {
            if (i == 0 || tail.size == MAX_WINDOW_MESSAGES) break
            var content = sanitizeForSdk(history[i].content)
            val bytes = content.toByteArray(Charsets.UTF_8).size
            if (bytes > budget) {
                if (tail.isNotEmpty()) break            // older turn doesn't fit: stop here
                content = truncateUtf8(content, budget) // lone newest message: cut, don't drop
            }
            budget -= content.toByteArray(Charsets.UTF_8).size
            tail.add(ChatMessage(role = history[i].role, content))
        }
        for (i in tail.indices.reversed()) window.add(tail[i])

        // We already know the input language (from on-device LID), so tell the model outright and
        // override any earlier-language turns still in the window.
        if (replyLanguage != null && window.isNotEmpty()) {
            val last = window.removeAt(window.lastIndex)
            window.add(ChatMessage(role = last.role, "[This message is in $replyLanguage. Reply only " +
                "in $replyLanguage, using its native script.]\n${last.content}"))
        }

        val templateOut = w.applyChatTemplate(window.toTypedArray(), null, false).getOrElse { e ->
            Log.e(TAG, "applyChatTemplate failed", e)
            history.removeAt(history.lastIndex)
            emit(ChatStream.Failed("The assistant could not read that message."))
            return@flow
        }

        val generation = GenerationConfig(
            maxTokens = 512,
            stopWords = null,
            stopCount = 0,
            nPast = 0,
            imagePaths = null,
            imageCount = 0,
            audioPaths = null,
            audioCount = 0,
        )

        val answer = StringBuilder()
        w.generateStreamFlow(templateOut.formattedText, generation).collect { result ->
            when (result) {
                is LlmStreamResult.Token -> {
                    answer.append(result.text)
                    emit(ChatStream.Token(result.text))
                }

                is LlmStreamResult.Completed -> {
                    // Sanitize before storing: streamed tokens can leave malformed multibyte
                    // fragments that would crash the NEXT turn's applyChatTemplate.
                    history.add(ChatMessage(role = "assistant", sanitizeForSdk(answer.toString())))
                    emit(ChatStream.Done)
                }

                is LlmStreamResult.Error -> {
                    Log.e(TAG, "generation error", result.throwable)
                    if (history.isNotEmpty() && history.last().role == "user") {
                        history.removeAt(history.lastIndex)
                    }
                    emit(ChatStream.Failed("The assistant stopped unexpectedly. Please try again."))
                }
            }
        }
    }.flowOn(Dispatchers.IO)

    /** Ask the native runtime to stop the in-flight generation early. */
    suspend fun stop() = withContext(Dispatchers.IO) {
        runCatching { wrapper?.stopStream() }
        Unit
    }

    /** Wipe the conversation but keep the model loaded. */
    suspend fun clearConversation() = withContext(Dispatchers.IO) {
        runCatching { wrapper?.reset() }
        resetHistory()
    }

    /** Release the native handle. Safe to call when nothing is loaded. */
    suspend fun unload() = lock.withLock {
        withContext(Dispatchers.IO) {
            runCatching {
                wrapper?.stopStream()
                wrapper?.destroy()
            }
            wrapper = null
            resetHistory()
        }
    }

    private fun resetHistory() {
        history.clear()
        history.add(ChatMessage(role = "system", SYSTEM_PROMPT))
    }

    /**
     * Make a string safe for GenieX's `applyChatTemplate`, which returns the formatted prompt to
     * Java via JNI `NewStringUTF` - that expects *Modified UTF-8* and hard-aborts (SIGABRT, "invalid
     * Modified UTF-8") on 4-byte characters (emoji / supplementary plane) and lone surrogates. Gemma
     * readily emits emoji, so once one lands in the replayed history the NEXT turn crashes the app.
     * We keep only valid BMP, non-surrogate, non-NUL code points (all Indic scripts are BMP, so
     * transcripts and native-script replies pass through unchanged); the live streamed tokens shown
     * in the UI are untouched - only the model-facing copy is cleaned. (The Qualcomm reference app
     * skips this because it was only exercised in ASCII English.)
     */
    private fun sanitizeForSdk(s: String): String {
        val sb = StringBuilder(s.length)
        var i = 0
        while (i < s.length) {
            val cp = s.codePointAt(i)
            i += Character.charCount(cp)
            if (cp != 0 && cp <= 0xFFFF && cp !in 0xD800..0xDFFF) sb.appendCodePoint(cp)
        }
        return sb.toString()
    }

    /**
     * Cut [s] down to at most [maxBytes] of UTF-8, always at a code-point boundary, so the
     * result can never start or end mid-character. Keeps the head of the message (questions
     * are front-loaded); only ever applied to a lone over-budget message, never mid-history.
     */
    private fun truncateUtf8(s: String, maxBytes: Int): String {
        var bytes = 0
        var i = 0
        while (i < s.length) {
            val cp = s.codePointAt(i)
            val cpBytes = when {
                cp <= 0x7F -> 1
                cp <= 0x7FF -> 2
                else -> 3 // sanitizeForSdk already dropped everything above the BMP
            }
            if (bytes + cpBytes > maxBytes) break
            bytes += cpBytes
            i += Character.charCount(cp)
        }
        return s.substring(0, i)
    }

    private companion object {
        const val TAG = "GenieXEngine"

        /** Most recent user/assistant messages replayed per turn (8 = 4 exchanges). Together
         *  with the 512-token output cap this keeps a turn comfortably inside nCtx = 2048. */
        const val MAX_WINDOW_MESSAGES = 8

        /**
         * UTF-8 byte budget for the replayed user/assistant turns (system prompt and the ~90-byte
         * LID tag are on top; both are pure ASCII). Sized so system prompt + window + 512 output
         * tokens stay inside nCtx = 2048 even for Devanagari/Tamil text (~3 bytes and roughly a
         * token per character), and well below whatever byte limit Genie's native templater trims
         * at - it must be the app, not Genie, that decides where text gets cut.
         */
        const val MAX_WINDOW_BYTES = 3_072

        /**
         * The assistant's brief. Kept deliberately short and factual for a small on-device
         * model. This is a fixed system instruction; the user's own typed questions are the
         * only other input and are never spliced into these instructions (CLAUDE.md #7).
         */
        const val SYSTEM_PROMPT =
            "You are Sahayak, a calm offline safety assistant inside the Sankat-Mochan mesh " +
                "app, running fully on the user's phone with no internet. People message you " +
                "during floods, fires, earthquakes and other emergencies. Give short, clear, " +
                "step-by-step guidance on safety, first aid, and staying reachable. If a " +
                "situation is life-threatening, tell them to tap the red SOS button on the home " +
                "screen to alert nearby responders over the mesh.\n\n" +
                "OFFLINE & TRUSTWORTHY: You run entirely on this phone and cannot make calls, browse " +
                "the internet, or look anything up - this is normal, not an error, so answer calmly " +
                "from your own general safety and first-aid knowledge. NEVER invent specific facts " +
                "you can't be sure of: do not make up helpline numbers, phone numbers, addresses, " +
                "names, dates, statistics, or current events. If you don't know something or it " +
                "needs local/live information you don't have, say so plainly and give the best " +
                "general safety guidance instead. It is better to admit uncertainty than to guess.\n\n" +
                "LANGUAGE: The user speaks in many different Indian languages (such as Hindi, " +
                "Tamil, Telugu, Kannada, Malayalam, Bengali, Marathi, Gujarati, Punjabi) or " +
                "English. Their message may be tagged with the language it is in. ALWAYS reply " +
                "in the SAME language and native script as the user's most recent message - if " +
                "they write in Tamil, reply only in Tamil; if in Hindi, reply only in Hindi. " +
                "Never switch to a different language than the user's latest message, and never " +
                "reply in English unless the user wrote in English. Reply in plain text only - " +
                "do NOT use emojis or pictographs."
    }
}
