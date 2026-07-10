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
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach

/**
 * Thin bridge between Compose and the mesh. Holds the single [BleMeshService]
 * for the app's lifetime and exposes its state flows straight to the UI.
 */
class MeshViewModel(app: Application) : AndroidViewModel(app) {

    private val service = BleMeshService(app)
    private val locationProvider = LocationProvider(app)

    val nodeId: String get() = service.nodeId

    // Which stage we've already raised a banner for, per SOS id, so each step notifies once.
    private val notifiedStage = HashMap<String, Int>()

    init {
        // When the mesh bumps one of *our* SOS messages to "reached control room" (1) or
        // "help on the way" (2), surface it as a real notification — the person may not be
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
        }
    }

    /** Latest GNSS fix, or null if we don't have one yet. Optional — an SOS
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
     * is already in hand when the SOS button is pressed — a request made at send time
     * would usually return nothing, because a cold fix without A-GPS takes a minute.
     * Safe to call only after ACCESS_FINE_LOCATION is granted.
     */
    private fun startLocation() {
        if (!locationProvider.isLocationEnabled()) {
            // Location is off: drop any fix we were holding so the indicator can't keep
            // claiming we're located. An SOS still sends fine without coordinates.
            clearFix()
            needsPreciseLocation = false
            locationStatus = "Location is switched off — turn it on in Settings. It works in aeroplane mode."
            return
        }
        if (!locationProvider.hasFineLocation() && !locationProvider.hasCoarseLocation()) {
            clearFix()
            needsPreciseLocation = false
            locationStatus = "Location permission was denied — grant it to send coordinates"
            return
        }
        // Granting "Approximate" instead of "Precise" leaves GPS_PROVIDER off-limits, which
        // used to fail silently behind a status line that claimed we were searching.
        if (!locationProvider.hasFineLocation()) {
            needsPreciseLocation = true
            locationStatus = "Only approximate location was allowed — switch to Precise for GPS coordinates"
        } else {
            needsPreciseLocation = false
            locationStatus = "Searching for satellites — the first fix can take a minute outdoors"
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
    val sent = service.store.sent
    val eventLog = service.store.eventLog
    val acceptedIds = service.store.acceptedIds
    val voiceClips = service.voiceClips.clips

    private val recorder = VoiceRecorder(app)

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
    }

    /** Stop and keep the clip. Nothing goes on air until the SOS button is pressed. */
    fun stopRecording() {
        if (!isRecording) return
        isRecording = false
        val clip = recorder.stop()
        if (clip == null) {
            voiceStatus = "Nothing recorded — hold the button while you speak"
            return
        }
        pendingVoice = clip
        voiceStatus = "Voice attached — it will be sent with your SOS"
    }

    fun discardVoice() {
        pendingVoice = null
        voiceStatus = ""
    }

    fun cancelRecording() {
        if (!isRecording) return
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
     * Order matters. The text envelope is one 104-byte frame — under a fifth of a second
     * on air — and carries the urgency and the coordinates. The audio is ~16 frames and
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
    }

    fun accept(sos: SosMessage) = service.accept(sos)

    override fun onCleared() {
        recorder.cancel()
        stopLocation()
        service.stop()
    }
}
