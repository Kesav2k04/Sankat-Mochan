package com.sankatmochan.mesh.mesh

import android.annotation.SuppressLint
import android.content.Context
import android.location.Location
import android.location.LocationManager
import android.util.Log

/**
 * Thin wrapper over the framework [LocationManager] — NO Google Play Services,
 * so no extra dependency and it works fully offline (GPS is satellite-only).
 *
 * We ask for a fresh GPS fix and fall back to the last known fix if a live one
 * isn't available yet (e.g. indoors / cold start). Caller must hold
 * ACCESS_FINE_LOCATION before invoking [fetchCurrent].
 */
@SuppressLint("MissingPermission")
class LocationProvider(context: Context) {

    private val appContext = context.applicationContext
    private val lm = appContext.getSystemService(Context.LOCATION_SERVICE) as LocationManager

    /** True if the user has location services switched on at the OS level. */
    fun isLocationEnabled(): Boolean = lm.isLocationEnabled

    /**
     * Fetch the device's current location. [onResult] is called on the main
     * thread with the [Location] (or null if unavailable). Non-blocking.
     */
    fun fetchCurrent(onResult: (Location?) -> Unit) {
        val provider = when {
            lm.allProviders.contains(LocationManager.GPS_PROVIDER) -> LocationManager.GPS_PROVIDER
            lm.allProviders.contains(LocationManager.NETWORK_PROVIDER) -> LocationManager.NETWORK_PROVIDER
            else -> {
                onResult(lastKnown())
                return
            }
        }
        try {
            // getCurrentLocation (API 30+) gets a single fresh fix, then times out.
            lm.getCurrentLocation(provider, null, appContext.mainExecutor) { loc ->
                onResult(loc ?: lastKnown())
            }
        } catch (e: Exception) {
            Log.w(TAG, "getCurrentLocation failed: ${e.message}")
            onResult(lastKnown())
        }
    }

    /** Best last-known fix across providers (may be stale, but better than nothing). */
    private fun lastKnown(): Location? {
        val providers = lm.getProviders(true)
        var best: Location? = null
        for (p in providers) {
            val loc = try { lm.getLastKnownLocation(p) } catch (e: Exception) { null }
            if (loc != null && (best == null || loc.time > best!!.time)) best = loc
        }
        return best
    }

    private companion object {
        const val TAG = "LocationProvider"
    }
}
