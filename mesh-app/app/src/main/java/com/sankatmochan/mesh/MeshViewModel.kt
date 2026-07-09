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

    /** Latest GPS fix, or null if we don't have one yet. Optional — an SOS
     *  sends fine without it (backward compatible). */
    var lat by mutableStateOf<Double?>(null)
        private set
    var lng by mutableStateOf<Double?>(null)
        private set
    /** Human-facing note about the location state, shown on the victim screen. */
    var locationStatus by mutableStateOf("Locating…")
        private set

    /** Ask for a fresh GPS fix. Safe to call only after ACCESS_FINE_LOCATION is granted. */
    fun refreshLocation() {
        if (!locationProvider.isLocationEnabled()) {
            locationStatus = "Location services are off — SOS will still send without coordinates"
            return
        }
        locationStatus = "Locating…"
        locationProvider.fetchCurrent { loc ->
            if (loc != null) {
                lat = loc.latitude
                lng = loc.longitude
                locationStatus = "GPS fix ±${loc.accuracy.toInt()}m"
            } else {
                locationStatus = "No GPS fix yet — move outdoors; SOS still sends without it"
            }
        }
    }

    val peerCount = service.store.peerCount
    val receivedSos = service.store.receivedSos
    val sent = service.store.sent
    val eventLog = service.store.eventLog

    /** null = still on the role-picker. */
    var role by mutableStateOf<MeshRole?>(null)
        private set

    fun bluetoothReady(): Boolean = service.isBluetoothReady()

    fun startAsRole(role: MeshRole) {
        this.role = role
        service.start(role)
    }

    fun leaveRole() {
        service.stop()
        role = null
    }

    fun sendSos(category: String, urgency: Int, gist: String, lang: String, locationHint: String) =
        service.sendSos(category, urgency, gist, lang, locationHint, lat, lng)

    fun accept(sos: SosMessage) = service.accept(sos)

    override fun onCleared() {
        service.stop()
    }
}
