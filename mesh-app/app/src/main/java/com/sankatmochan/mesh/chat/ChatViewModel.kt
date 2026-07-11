package com.sankatmochan.mesh.chat

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/**
 * Drives the offline assistant screen: SDK bring-up, one-time model download, load, and
 * streaming chat. All GenieX specifics stay inside [GenieXEngine]; this class only ever
 * exposes plain UI state, so the Compose layer knows nothing about the native runtime.
 */
class ChatViewModel(app: Application) : AndroidViewModel(app) {

    private val engine = GenieXEngine(app)

    /** Survives [onCleared] so we can release the native handle even as the VM scope dies. */
    private val cleanupScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    enum class Phase {
        /** SDK is coming up. */
        INITIALIZING,

        /** This device/build can't run the on-device model. Terminal; see [statusMessage]. */
        UNSUPPORTED,

        /** SDK is up but the selected model's weights aren't on the phone yet. */
        NEEDS_MODEL,

        /** Weights are downloading; see [downloadPercent]. */
        DOWNLOADING,

        /** Weights are on disk and being loaded into a native handle. */
        LOADING,

        /** Ready to chat. */
        READY,

        /** Load failed after a successful download. Retryable; see [statusMessage]. */
        LOAD_FAILED,
    }

    enum class Role { USER, ASSISTANT }

    data class UiMessage(
        val role: Role,
        val text: String,
        val streaming: Boolean = false,
        val isError: Boolean = false,
    )

    var phase by mutableStateOf(Phase.INITIALIZING)
        private set

    /** User-safe status text for the UNSUPPORTED / LOAD_FAILED / download-error states. */
    var statusMessage by mutableStateOf("")
        private set

    var downloadPercent by mutableStateOf(0)
        private set

    var selectedModel by mutableStateOf(AssistantModels.default)
        private set

    /** Run inference on the Snapdragon NPU (default) or fall back to CPU. */
    var runOnNpu by mutableStateOf(true)
        private set

    var isGenerating by mutableStateOf(false)
        private set

    /** True while a picked local file is being copied in and validated (see [importLocalModel]). */
    var isImporting by mutableStateOf(false)
        private set

    val messages = mutableStateListOf<UiMessage>()

    /** GGUF files the user has side-loaded onto the phone, shown alongside the hub catalogue. */
    val localModels = mutableStateListOf<AssistantModel>()

    private var downloadJob: Job? = null
    private var generateJob: Job? = null

    init {
        bootstrap()
    }

    // ── Bring-up ────────────────────────────────────────────────────────────────

    fun bootstrap() {
        viewModelScope.launch {
            phase = Phase.INITIALIZING
            refreshLocalModels()
            when (val result = engine.initialize()) {
                is GenieXEngine.InitResult.Unsupported -> {
                    statusMessage = result.reason
                    phase = Phase.UNSUPPORTED
                }

                GenieXEngine.InitResult.Ready -> evaluateModel()
            }
        }
    }

    /** Re-scan device storage for side-loaded `.gguf` files. */
    fun refreshLocalModels() {
        viewModelScope.launch {
            val found = engine.scanLocalModels()
            localModels.clear()
            localModels.addAll(found)
        }
    }

    /** Import a user-picked model file, then select and load it (plug-and-play). */
    fun importLocalModel(uri: android.net.Uri, suggestedName: String) {
        if (isGenerating || isImporting || phase == Phase.DOWNLOADING) return
        viewModelScope.launch {
            isImporting = true
            try {
                when (val result = engine.importModel(uri, suggestedName)) {
                    is GenieXEngine.ImportResult.Ok -> {
                        val imported = result.model
                        if (localModels.none { it.id == imported.id }) localModels.add(0, imported)
                        if (phase == Phase.UNSUPPORTED) return@launch
                        engine.unload()
                        messages.clear()
                        selectedModel = imported
                        evaluateModel()
                    }

                    GenieXEngine.ImportResult.UnsupportedFormat -> {
                        statusMessage = "Only .gguf model files are supported right now."
                        phase = Phase.NEEDS_MODEL
                    }

                    GenieXEngine.ImportResult.Failed -> {
                        statusMessage = "Could not import that file. Make sure it is a .gguf model."
                        phase = Phase.NEEDS_MODEL
                    }
                }
            } finally {
                isImporting = false
            }
        }
    }

    /** After init (or a model switch): auto-load if the weights are cached, else ask to download. */
    private suspend fun evaluateModel() {
        phase = if (engine.isDownloaded(selectedModel)) {
            loadCurrent()
            return
        } else {
            Phase.NEEDS_MODEL
        }
    }

    // ── Model selection / download / load ───────────────────────────────────────

    fun selectModel(model: AssistantModel) {
        if (model.id == selectedModel.id || isGenerating || isImporting || phase == Phase.DOWNLOADING) return
        viewModelScope.launch {
            downloadJob?.cancel()
            engine.unload()
            messages.clear()
            selectedModel = model
            if (phase == Phase.UNSUPPORTED) return@launch
            evaluateModel()
        }
    }

    fun chooseCompute(enabled: Boolean) {
        if (enabled == runOnNpu || isGenerating || isImporting || phase == Phase.DOWNLOADING) return
        runOnNpu = enabled
        // The compute unit is baked in at load time, so re-load if a model is already up.
        if (phase == Phase.READY || phase == Phase.LOAD_FAILED) {
            viewModelScope.launch {
                engine.unload()
                messages.clear()
                loadCurrent()
            }
        }
    }

    fun download() {
        if (phase == Phase.DOWNLOADING || isImporting) return
        val model = selectedModel
        downloadJob = viewModelScope.launch {
            phase = Phase.DOWNLOADING
            downloadPercent = 0
            try {
                engine.downloadFlow(model).collect { pct -> downloadPercent = pct }
                loadCurrent()
            } catch (e: kotlinx.coroutines.CancellationException) {
                phase = Phase.NEEDS_MODEL
                throw e
            } catch (e: Exception) {
                statusMessage = "Download failed. Check your connection and try again."
                phase = Phase.NEEDS_MODEL
            }
        }
    }

    fun cancelDownload() {
        downloadJob?.cancel()
        downloadJob = null
        phase = Phase.NEEDS_MODEL
    }

    private suspend fun loadCurrent() {
        phase = Phase.LOADING
        when (val result = engine.load(selectedModel, runOnNpu)) {
            GenieXEngine.LoadResult.Ok -> {
                phase = Phase.READY
                if (messages.isEmpty()) postGreeting()
            }

            is GenieXEngine.LoadResult.Failed -> {
                statusMessage = result.message
                phase = Phase.LOAD_FAILED
            }
        }
    }

    fun retryLoad() {
        if (phase != Phase.LOAD_FAILED) return
        viewModelScope.launch { loadCurrent() }
    }

    // ── Chat ────────────────────────────────────────────────────────────────────

    fun send(rawText: String) {
        // Size-cap untrusted input before it reaches the model (CLAUDE.md #8) — a huge paste
        // would otherwise eat the whole context window in one turn.
        val text = rawText.trim().take(MAX_INPUT_CHARS)
        if (text.isEmpty() || isGenerating || phase != Phase.READY) return

        messages.add(UiMessage(Role.USER, text))
        messages.add(UiMessage(Role.ASSISTANT, "", streaming = true))
        isGenerating = true

        generateJob = viewModelScope.launch {
            try {
                engine.replyFlow(text).collect { chunk ->
                    when (chunk) {
                        is GenieXEngine.ChatStream.Token ->
                            updateAssistant { it.copy(text = it.text + chunk.text) }

                        GenieXEngine.ChatStream.Done ->
                            updateAssistant { it.copy(streaming = false) }

                        is GenieXEngine.ChatStream.Failed ->
                            updateAssistant {
                                it.copy(text = chunk.message, streaming = false, isError = true)
                            }
                    }
                }
            } finally {
                // Guard against a dangling spinner if the flow ends without a terminal event.
                updateAssistant { if (it.streaming) it.copy(streaming = false) else it }
                isGenerating = false
            }
        }
    }

    fun stop() {
        if (!isGenerating) return
        // Ask the native runtime to wind down; the flow then completes and clears isGenerating.
        viewModelScope.launch { engine.stop() }
    }

    fun clearChat() {
        if (isGenerating || phase != Phase.READY) return
        viewModelScope.launch {
            engine.clearConversation()
            messages.clear()
            postGreeting()
        }
    }

    /** A display-only opener so the screen never starts blank. Not part of model context. */
    private fun postGreeting() {
        messages.add(
            UiMessage(
                role = Role.ASSISTANT,
                text = "I'm Sahayak, your offline safety assistant. Ask me about first aid, " +
                    "staying safe in a flood, fire or earthquake, or how to use the mesh. " +
                    "In a life-threatening emergency, tap the red SOS button on the home screen.",
            )
        )
    }

    /** Replace the trailing assistant bubble via [transform]. No-op if it isn't there. */
    private inline fun updateAssistant(transform: (UiMessage) -> UiMessage) {
        val i = messages.lastIndex
        if (i < 0) return
        val current = messages[i]
        if (current.role != Role.ASSISTANT) return
        messages[i] = transform(current)
    }

    private companion object {
        /** Hard cap on one typed message — plenty for a real question, small enough that a
         *  single turn can never dominate the model's context window. */
        const val MAX_INPUT_CHARS = 1000
    }

    override fun onCleared() {
        super.onCleared()
        cleanupScope.launch {
            engine.unload()
            cleanupScope.cancel()
        }
    }
}
