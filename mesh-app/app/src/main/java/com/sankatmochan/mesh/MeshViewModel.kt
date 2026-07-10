package com.sankatmochan.mesh

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import com.sankatmochan.mesh.mesh.BleMeshService
import com.sankatmochan.mesh.mesh.LocationProvider
import com.sankatmochan.mesh.mesh.MeshRole
import com.sankatmochan.mesh.model.SosMessage

/**
 * Thin bridge between Compose and the mesh. Holds the single [BleMeshService]
 * for the app's lifetime and exposes its state flows straight to the UI.
 */
class MeshViewModel(app: Application) : AndroidViewModel(app) {

    private val service = BleMeshService(app)
    private val locationProvider = LocationProvider(app)

    val nodeId: String get() = service.nodeId

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
            locationStatus = "Location is switched off — turn it on in Settings. It works in aeroplane mode."
            return
        }
        if (!locationProvider.hasFineLocation() && !locationProvider.hasCoarseLocation()) {
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

    /** True when this phone refuses to peer with other phones, forcing traffic
     *  out through the LoRa gateway. See [BleMeshService.loraOnly]. */
    val loraOnly = service.loraOnly

    fun setLoraOnly(enabled: Boolean) = service.setLoraOnly(enabled)

    /** null = still on the role-picker. */
    var role by mutableStateOf<MeshRole?>(null)
        private set

    fun bluetoothReady(): Boolean = service.isBluetoothReady()

    fun startAsRole(role: MeshRole) {
        this.role = role
        service.start(role)
        // The victim's fix travels in the SOS; the responder's fix is what turns a pair
        // of coordinates into "420 m northeast of you". A relay needs neither, so it
        // does not pay for a running GNSS receiver.
        if (role == MeshRole.VICTIM || role == MeshRole.RESPONDER) startLocation()
    }

    fun leaveRole() {
        stopLocation()
        service.stop()
        role = null
    }

    fun sendSos(category: String, urgency: Int, gist: String, lang: String, locationHint: String) =
        service.sendSos(category, urgency, gist, lang, locationHint, lat, lng)

    fun accept(sos: SosMessage) = service.accept(sos)

    override fun onCleared() {
        stopLocation()
        service.stop()
    }
}
