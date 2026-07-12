package com.sankatmochan.mesh

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.sankatmochan.mesh.mesh.BleMeshService
import com.sankatmochan.mesh.mesh.LocationProvider
import com.sankatmochan.mesh.mesh.MeshRole
import com.sankatmochan.mesh.mesh.SentSos
import com.sankatmochan.mesh.mesh.VoiceRecorder
import com.sankatmochan.mesh.model.SosMessage
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.launch

/**
 * Thin bridge between Compose and the mesh. Holds the single [BleMeshService]
 * for the app's lifetime and exposes its state flows straight to the UI.
 */
class MeshViewModel(app: Application) : AndroidViewModel(app) {

    private val service = BleMeshService(app)
    private val locationProvider = LocationProvider(app)

    /** The post-SOS victim agent (Sahayak). Starts automatically after every SOS this phone
     *  originates; sends validated TAGS follow-ups through the mesh service. */
    val agent = com.sankatmochan.mesh.agent.SahayakAgent(
        app = app,
        scope = viewModelScope,
        sendTags = { tags, urgency ->
            lastSentSos?.let { service.sendAgentTags(it, tags, urgency) }
        },
    )

    /** The SOS the current agent session is anchored to (this phone's most recent send). */
    private var lastSentSos: SosMessage? = null

    val nodeId: String get() = service.nodeId

    /** Stable id of this device, sent with every SOS. Shown on the sent confirmation. */
    val deviceId: String get() = service.deviceId

    // Which stage we've already raised a banner for, per SOS id, so each step notifies once.
    private val notifiedStage = HashMap<String, Int>()

    /**
     * Bumped once each time the app is reopened after genuinely leaving the foreground (see
     * [beginNewSession]). The victim console observes it to fold its transient send/echo UI back
     * to the calm home state, so a reopened app never opens onto the last session's SOS. It is a
     * plain counter rather than a boolean so every reopen is a distinct, observable event.
     */
    var sessionEpoch by mutableStateOf(0)
        private set

    /**
     * End the current SOS session and start a clean one. Drops the sent-SOS list so the console
     * reads READY again, forgets which status banners we have already shown, and signals the UI
     * (via [sessionEpoch]) to reset its transient state. Called by [MainActivity] when the app
     * returns from the background - never on a configuration change or one of our own outward
     * excursions (the battery-saver bounce right after a send), so an in-flight SOS is only ever
     * cleared when the user has actually left the app and come back.
     */
    fun beginNewSession() {
        // An engaged Sahayak-agent session is exempt: a panicking victim pocketing the phone
        // mid-conversation (or mid-check-in) and reopening it must NOT lose the SOS id the
        // agent's follow-ups and the ACCEPTED status match on, nor kill the silent-escalation
        // timers. The session resets only once the agent is idle.
        if (agent.isEngaged) return
        service.store.clearSent()
        notifiedStage.clear()
        lastSentSos = null
        agent.endSession()
        // A half-recorded clip or an unsent attachment from before we left is last-session state
        // too - drop it, and make sure no microphone is left live behind a reopened console.
        cancelRecording()
        discardVoice()
        sessionEpoch++
    }

    init {
        // When the mesh bumps one of *our* SOS messages to "reached control room" (1) or
        // "help on the way" (2), surface it as a real notification - the person may not be
        // watching the screen. Only the origin phone holds the SOS in `sent`, so this only
        // ever fires for the victim who sent it.
        service.store.sent
            .onEach { list -> list.forEach(::maybeNotify) }
            .launchIn(viewModelScope)
    }

    private fun maybeNotify(s: SentSos) {
        val already = notifiedStage[s.message.id] ?: 0
        if (s.stage in 1..2 && s.stage > already) {
            notifiedStage[s.message.id] = s.stage
            RescueNotifier.notifyStatus(getApplication<Application>(), s)
            // Feed the real status to the agent — it relays it as reassurance (never invents).
            if (s.message.id == lastSentSos?.id) agent.onStatus(s.stage, s.statusText)
        }
    }

    /** Latest GNSS fix, or null if we don't have one yet. Optional - an SOS
     *  sends fine without it, and is never blocked waiting for one. */
    var lat by mutableStateOf<Double?>(null)
        private set
    var lng by mutableStateOf<Double?>(null)
        private set
    /** Wall-clock time of the current fix, for showing how stale it is. */
    var fixTime by mutableStateOf<Long?>(null)
        private set
    /** Human-facing note about the location state, shown on the victim screen. */
    var locationStatus by mutableStateOf("Searching for satellites…")
        private set

    /** True when the user granted "Approximate" rather than "Precise" location, which
     *  locks us out of GPS entirely. The UI offers a way to fix it. */
    var needsPreciseLocation by mutableStateOf(false)
        private set

    /**
     * Keep the GNSS receiver warm. Called as soon as the victim role starts, so a fix
     * is already in hand when the SOS button is pressed - a request made at send time
     * would usually return nothing, because a cold fix without A-GPS takes a minute.
     * Safe to call only after ACCESS_FINE_LOCATION is granted.
     */
    private fun startLocation() {
        if (!locationProvider.isLocationEnabled()) {
            // Location is off: drop any fix we were holding so the indicator can't keep
            // claiming we're located. An SOS still sends fine without coordinates.
            clearFix()
            needsPreciseLocation = false
            locationStatus = "Location is switched off - turn it on in Settings. It works in aeroplane mode."
            return
        }
        if (!locationProvider.hasFineLocation() && !locationProvider.hasCoarseLocation()) {
            clearFix()
            needsPreciseLocation = false
            locationStatus = "Location permission was denied - grant it to send coordinates"
            return
        }
        // Granting "Approximate" instead of "Precise" leaves GPS_PROVIDER off-limits, which
        // used to fail silently behind a status line that claimed we were searching.
        if (!locationProvider.hasFineLocation()) {
            needsPreciseLocation = true
            locationStatus = "Only approximate location was allowed - switch to Precise for GPS coordinates"
        } else {
            needsPreciseLocation = false
            locationStatus = "Searching for satellites - the first fix can take a minute outdoors"
        }

        val started = locationProvider.start(
            onFix = { loc ->
                lat = loc.latitude
                lng = loc.longitude
                fixTime = System.currentTimeMillis()
            },
            onStatus = { locationStatus = it }
        )
        if (started.isEmpty()) {
            locationStatus = "No location source is available on this phone"
        }
    }

    private fun stopLocation() {
        locationProvider.stop()
    }

    /** Forget the last GPS fix so nothing downstream (the location indicator, the SOS
     *  envelope) can present a stale position as if it were live. */
    private fun clearFix() {
        lat = null
        lng = null
        fixTime = null
    }

    /** Re-check after the operator turns Location on from the system settings. */
    fun refreshLocation() {
        stopLocation()
        startLocation()
    }

    val peerCount = service.store.peerCount
    val receivedSos = service.store.receivedSos
    val agentTags = service.store.agentTags
    val sent = service.store.sent
    val eventLog = service.store.eventLog
    val acceptedIds = service.store.acceptedIds
    val voiceClips = service.voiceClips.clips

    private val recorder = VoiceRecorder(app)

    /** Owns the 10 s airtime cap. Lives here, not in the voice tile's LaunchedEffect, because the
     *  tile leaves composition the instant the SOS radar/map takes over - which would otherwise
     *  strand a live recording (mic held, no auto-stop). See [startRecording]. */
    private var autoStopJob: Job? = null

    init {
        // OS backstop: if the coroutine timer ever fails to fire, MediaRecorder's own
        // setMaxDuration still stops encoding at the cap - fold that back into our state so the
        // recorder is released and the clip is kept.
        recorder.onMaxDurationReached = { stopRecording() }
    }

    var isRecording by mutableStateOf(false)
        private set
    var voiceStatus by mutableStateOf("")
        private set

    /** A recorded clip waiting to be sent. It travels with the next SOS, not on its own,
     *  so the rescuer always gets the coordinates and urgency before the audio. */
    var pendingVoice by mutableStateOf<ByteArray?>(null)
        private set

    val pendingVoiceBytes: Int get() = pendingVoice?.size ?: 0

    /** Begin recording. The caller must already hold RECORD_AUDIO. */
    fun startRecording() {
        if (isRecording) return
        if (!recorder.start()) {
            voiceStatus = "Could not open the microphone"
            return
        }
        isRecording = true
        voiceStatus = "Recording…"
        // Stop at the airtime cap no matter what happens to the UI. Cancelled by any explicit
        // stop/cancel so it never fires against a fresh recording.
        autoStopJob?.cancel()
        autoStopJob = viewModelScope.launch {
            delay(VoiceRecorder.MAX_MILLIS.toLong())
            stopRecording()
        }
    }

    /** Tap-to-toggle from the voice tile: start if idle, stop and keep the clip if recording. */
    fun toggleRecording() {
        if (isRecording) stopRecording() else startRecording()
    }

    /** Stop and keep the clip. Nothing goes on air until the SOS button is pressed. */
    fun stopRecording() {
        if (!isRecording) return
        autoStopJob?.cancel()
        autoStopJob = null
        isRecording = false
        val clip = recorder.stop()
        if (clip == null) {
            voiceStatus = "Nothing recorded - tap to start, speak, then tap again"
            return
        }
        pendingVoice = clip
        voiceStatus = "Voice attached - it will be sent with your SOS"
    }

    fun discardVoice() {
        pendingVoice = null
        voiceStatus = ""
    }

    fun cancelRecording() {
        if (!isRecording) return
        autoStopJob?.cancel()
        autoStopJob = null
        isRecording = false
        recorder.cancel()
        voiceStatus = ""
    }

    /** True when this phone refuses to peer with other phones, forcing traffic
     *  out through the LoRa gateway. See [BleMeshService.loraOnly]. */
    val loraOnly = service.loraOnly

    fun setLoraOnly(enabled: Boolean) = service.setLoraOnly(enabled)

    /** null = not started yet. The app boots straight into VICTIM; the settings modal
     *  flips between VICTIM (the user) and RESPONDER. */
    var role by mutableStateOf<MeshRole?>(null)
        private set

    fun bluetoothReady(): Boolean = service.isBluetoothReady()

    /**
     * Start, or switch, this phone's job. Idempotent: re-selecting the current role does
     * nothing. Switching between two live roles tears the old one down first, because
     * [BleMeshService.start] is a no-op while already running and would otherwise leave the
     * advertisement stuck on the previous role.
     */
    fun selectRole(role: MeshRole) {
        if (this.role == role) return
        if (this.role != null) {
            stopLocation()
            service.stop()
        }
        this.role = role
        service.start(role)
        // The victim's fix travels in the SOS; the responder's fix is what turns a pair
        // of coordinates into "420 m northeast of you". A relay needs neither, so it
        // does not pay for a running GNSS receiver.
        if (role == MeshRole.VICTIM || role == MeshRole.RESPONDER) startLocation()
    }

    /**
     * Send the SOS, then the attached recording if there is one.
     *
     * Order matters. The text envelope is one 104-byte frame - under a fifth of a second
     * on air - and carries the urgency and the coordinates. The audio is ~16 frames and
     * several seconds. The rescuer must have the actionable part before the channel
     * disappears under the clip.
     */
    fun sendSos(category: String, urgency: Int, gist: String, lang: String, locationHint: String) {
        service.sendSos(category, urgency, gist, lang, locationHint, lat, lng)
        pendingVoice?.let { clip ->
            service.sendVoice(clip, VoiceRecorder.CODEC)
            pendingVoice = null
            voiceStatus = "Voice message sent with your SOS (${clip.size} bytes)"
        }
        // The SOS is already ON AIR (above) — only now does the agent open its conversation.
        // Everything the agent produces is additive follow-up data on this SOS.
        service.store.sent.value.lastOrNull()?.let { sentSos ->
            lastSentSos = sentSos.message
            agent.start(sentSos.message)
        }
    }

    fun accept(sos: SosMessage) = service.accept(sos)

    override fun onCleared() {
        agent.endSession()
        recorder.cancel()
        stopLocation()
        service.stop()
    }
}
