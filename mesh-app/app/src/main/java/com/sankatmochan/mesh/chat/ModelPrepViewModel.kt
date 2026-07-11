package com.sankatmochan.mesh.chat

import android.app.ActivityManager
import android.app.Application
import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

/**
 * Powers the "prepare for offline" helper reachable from the home screen's info button.
 *
 * The idea: nudge people to pull a safety-assistant model *while they still have signal*, so it
 * is already on the phone when an emergency knocks them offline. It picks a sensible model for
 * the device (RAM-aware), then downloads it with a visible progress bar and a rolling activity
 * log, reusing the exact same GenieX pull path as the assistant screen ([GenieXEngine]) so the
 * weights land in the shared cache and the chat loads them instantly later.
 *
 * This VM never *loads* a model into a native handle - it only downloads - so it can run
 * alongside the assistant without fighting over the single LLM handle.
 */
class ModelPrepViewModel(app: Application) : AndroidViewModel(app) {

    private val engine = GenieXEngine(app)

    enum class Phase {
        /** Bringing the runtime up / checking what's already on disk. */
        CHECKING,

        /** Runtime up, model not yet on the phone - offer to download. */
        READY_TO_DOWNLOAD,

        /** Pulling weights; see [percent]. */
        DOWNLOADING,

        /** The recommended model is already downloaded and ready. */
        ALREADY_READY,

        /** Just finished a successful download. */
        DONE,

        /** This device/build can't run on-device AI at all. */
        UNSUPPORTED,

        /** Download failed; retryable. */
        FAILED,
    }

    var phase by mutableStateOf(Phase.CHECKING)
        private set

    var percent by mutableStateOf(0)
        private set

    /** The model we recommend for this phone. */
    var recommended by mutableStateOf(AssistantModels.default)
        private set

    /** Detected device memory, shown so the recommendation reads as reasoned, not arbitrary. */
    var deviceRamGb by mutableStateOf(0.0)
        private set

    /** Human-readable, append-only activity log shown under the progress bar. */
    val log = mutableStateListOf<String>()

    private var job: Job? = null
    private var started = false

    /** Called when the sheet opens. Idempotent - a re-open won't restart a running download. */
    fun open() {
        if (started) return
        started = true
        recommended = pickForDevice()
        viewModelScope.launch {
            phase = Phase.CHECKING
            addLog("Detected ${"%.1f".format(deviceRamGb)} GB RAM - recommending ${recommended.displayName}")
            addLog("Bringing up the on-device runtime…")
            when (engine.initialize()) {
                is GenieXEngine.InitResult.Unsupported -> {
                    addLog("On-device AI isn't available on this device.")
                    phase = Phase.UNSUPPORTED
                }

                GenieXEngine.InitResult.Ready -> {
                    if (engine.isDownloaded(recommended)) {
                        addLog("${recommended.displayName} is already on your phone - you're set for offline.")
                        phase = Phase.ALREADY_READY
                    } else {
                        addLog("Ready. Tap download to save ${recommended.displayName} (${recommended.approxSize}).")
                        phase = Phase.READY_TO_DOWNLOAD
                    }
                }
            }
        }
    }

    /** Download the given model (defaults to the recommendation) with progress + log. */
    fun download(model: AssistantModel = recommended) {
        if (phase == Phase.DOWNLOADING) return
        recommended = model
        job = viewModelScope.launch {
            phase = Phase.DOWNLOADING
            percent = 0
            addLog("Downloading ${model.displayName} - keep this open…")
            try {
                var lastLogged = -1
                engine.downloadFlow(model).collect { pct ->
                    percent = pct
                    // Log at coarse milestones so the feed reads as progress, not spam.
                    if (pct / 25 > lastLogged / 25) {
                        addLog("$pct% downloaded")
                        lastLogged = pct
                    }
                }
                addLog("Saved. ${model.displayName} now works fully offline.")
                phase = Phase.DONE
            } catch (e: kotlinx.coroutines.CancellationException) {
                addLog("Download cancelled.")
                phase = Phase.READY_TO_DOWNLOAD
                throw e
            } catch (e: Exception) {
                addLog("Download failed - check your connection and try again.")
                phase = Phase.FAILED
            }
        }
    }

    fun cancel() {
        job?.cancel()
        job = null
        if (phase == Phase.DOWNLOADING) phase = Phase.READY_TO_DOWNLOAD
    }

    private fun addLog(line: String) {
        log.add(line)
        // Keep the feed bounded so a long session can't grow it without limit.
        while (log.size > 40) log.removeAt(0)
    }

    /**
     * Recommend a model for this device. All catalogue models are small quantised chat models,
     * so the driver is really "how much headroom does this phone have": pick the larger, better
     * Gemma on a roomy device, the standard one otherwise. Also stashes [deviceRamGb] for the UI.
     */
    private fun pickForDevice(): AssistantModel {
        val am = getApplication<Application>()
            .getSystemService(Context.ACTIVITY_SERVICE) as? ActivityManager
        val mi = ActivityManager.MemoryInfo()
        am?.getMemoryInfo(mi)
        deviceRamGb = mi.totalMem / 1_000_000_000.0
        return when {
            // Plenty of headroom → the larger Gemma answers better.
            deviceRamGb >= 7.0 ->
                AssistantModels.byId("gemma-4-E4B") ?: AssistantModels.default
            // Comfortable → the recommended default (Gemma E2B).
            else -> AssistantModels.default
        }
    }

    override fun onCleared() {
        super.onCleared()
        // We never loaded a handle, but releasing is cheap and safe.
        viewModelScope.launch { engine.unload() }
    }
}
