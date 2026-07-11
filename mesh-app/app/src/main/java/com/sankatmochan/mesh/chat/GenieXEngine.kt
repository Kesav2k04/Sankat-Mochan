package com.sankatmochan.mesh.chat

import android.content.Context
import android.util.Log
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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.IOException
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
 * Every method is safe to call from a coroutine on any dispatcher — the heavy work is moved
 * onto [Dispatchers.IO] internally. Instances are cheap; hold one per assistant session.
 */
class GenieXEngine(context: Context) {

    private val appContext = context.applicationContext

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

    /** Bring the SDK up once. Idempotent — repeated calls after a success return [Ready]. */
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
            // Generic, user-safe message — the real reason is only in Logcat (CLAUDE.md #10).
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

    /** True when the model's weights are already fully pulled into the manager's cache. */
    suspend fun isDownloaded(model: AssistantModel): Boolean = withContext(Dispatchers.IO) {
        runCatching { ModelManagerWrapper.getPaths(model.modelName) != null }.getOrDefault(false)
    }

    /**
     * Download [model]'s weights, emitting whole-percent progress (0..100). Resumable: a
     * cancelled collection leaves partial files on disk for the next call to continue. Throws
     * [IOException] on a hub error so the caller can show a retry.
     */
    fun downloadFlow(model: AssistantModel): Flow<Int> = flow {
        val hub = runCatching { HubSource.valueOf(model.hub) }.getOrDefault(HubSource.AUTO)
        val input = ModelPullInput(
            model_name = model.modelName,
            precision = model.quant,
            hub = hub,
            chipset = null,       // GGUF/HuggingFace pulls are chipset-agnostic.
            display_name = null,
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
            val paths = runCatching { ModelManagerWrapper.getPaths(model.modelName) }.getOrNull()
                ?: return@withContext LoadResult.Failed("Model files are missing — download it again.")

            // A GGUF pull writes no runtime manifest, so fall back to the llama.cpp runtime.
            val runtimeId = paths.runtime_id.ifEmpty { "llama_cpp" }
            val config = ModelConfig(
                nCtx = 1024,
                nGpuLayers = if (onNpu) 999 else 0,
                enable_thinking = false,
            )
            val built = LlmWrapper.builder()
                .llmCreateInput(
                    LlmCreateInput(
                        model_name = paths.model_name,
                        model_path = paths.model_path,
                        tokenizer_path = paths.tokenizer_path,
                        config = config,
                        runtime_id = runtimeId,
                        compute_unit = ComputeUnitValue.NPU.value,
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
     * once per send — the ViewModel guards against overlapping generations.
     */
    fun replyFlow(userText: String): Flow<ChatStream> = flow {
        val w = wrapper
        if (w == null) {
            emit(ChatStream.Failed("No model is loaded."))
            return@flow
        }

        history.add(ChatMessage(role = "user", userText))

        val templateOut = w.applyChatTemplate(history.toTypedArray(), null, false).getOrElse { e ->
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
                    history.add(ChatMessage(role = "assistant", answer.toString()))
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

    private companion object {
        const val TAG = "GenieXEngine"

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
                "screen to alert nearby responders over the mesh. You cannot make phone calls " +
                "or reach the internet. If you are unsure, say so plainly rather than guessing."
    }
}
