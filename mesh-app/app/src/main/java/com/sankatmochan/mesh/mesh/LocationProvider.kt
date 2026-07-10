package com.sankatmochan.mesh.mesh

import android.annotation.SuppressLint
import android.content.Context
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.util.Log

/**
 * Thin wrapper over the framework [LocationManager] — NO Google Play Services, so no
 * extra dependency and it works fully offline. GNSS is receive-only, so it keeps
 * working in aeroplane mode; what aeroplane mode costs us is the assistance data
 * (A-GPS) that normally arrives over the network, which is why a cold first fix can
 * take a minute rather than a second.
 *
 * Two deliberate choices follow from that:
 *
 *  - **GPS_PROVIDER only.** NETWORK_PROVIDER needs cell towers or Wi-Fi and produces
 *    nothing offline. Worse, it can return a coarse fix from wherever the phone last
 *    had signal. Sending a rescue team to a stale network fix is worse than sending
 *    them no coordinates at all.
 *
 *  - **Keep the receiver warm.** We subscribe to updates the moment the victim role
 *    starts, not when the SOS button is pressed, so the fix is already there when it
 *    matters. A one-shot request at send time would usually return nothing.
 *
 * Caller must hold ACCESS_FINE_LOCATION. Coarse-only grants do not drive GPS_PROVIDER.
 */
@SuppressLint("MissingPermission")
class LocationProvider(context: Context) {

    private val appContext = context.applicationContext
    private val lm = appContext.getSystemService(Context.LOCATION_SERVICE) as LocationManager
    private var listener: LocationListener? = null

    /** True if the user has location services switched on at the OS level. */
    fun isLocationEnabled(): Boolean = lm.isLocationEnabled

    /** True if this device exposes a GNSS receiver at all. */
    fun hasGps(): Boolean = lm.allProviders.contains(LocationManager.GPS_PROVIDER)

    /**
     * Subscribe to GNSS fixes until [stop]. [onFix] is called on the main thread for
     * every fix, starting with a recent last-known one if we have it. Idempotent.
     */
    fun start(onFix: (Location) -> Unit) {
        if (listener != null) return
        if (!hasGps()) {
            Log.w(TAG, "device has no GPS provider")
            return
        }

        // Seed immediately from the last GNSS fix, but only if it is recent enough to
        // still describe where the phone is.
        freshLastKnownGps()?.let(onFix)

        val l = LocationListener { loc -> onFix(loc) }
        listener = l
        try {
            lm.requestLocationUpdates(
                LocationManager.GPS_PROVIDER,
                MIN_INTERVAL_MS,
                MIN_DISTANCE_M,
                l,
                appContext.mainLooper
            )
        } catch (e: Exception) {
            Log.w(TAG, "requestLocationUpdates failed: ${e.message}")
            listener = null
        }
    }

    fun stop() {
        val l = listener ?: return
        listener = null
        try {
            lm.removeUpdates(l)
        } catch (e: Exception) {
            Log.w(TAG, "removeUpdates failed: ${e.message}")
        }
    }

    /** The last GNSS fix, if it is recent enough to be worth acting on. */
    private fun freshLastKnownGps(): Location? {
        val loc = try {
            lm.getLastKnownLocation(LocationManager.GPS_PROVIDER)
        } catch (e: Exception) {
            null
        } ?: return null
        val age = System.currentTimeMillis() - loc.time
        return if (age in 0..MAX_SEED_AGE_MS) loc else null
    }

    private companion object {
        const val TAG = "LocationProvider"
        const val MIN_INTERVAL_MS = 1_000L
        const val MIN_DISTANCE_M = 0f
        /** Beyond this, a last-known fix says where you *were*, not where you are. */
        const val MAX_SEED_AGE_MS = 2 * 60 * 1000L
    }
}
