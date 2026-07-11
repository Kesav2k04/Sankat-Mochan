package com.sankatmochan.mesh.mesh

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.location.GnssStatus
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.CancellationSignal
import android.util.Log
import androidx.core.content.ContextCompat

/**
 * Location without Google Play Services — the framework [LocationManager] only, so no
 * extra dependency and nothing that needs a network.
 *
 * GNSS is a receive-only radio, so it keeps working in aeroplane mode. What aeroplane
 * mode costs is A-GPS: the almanac and rough time/position that normally arrive over
 * the network. Without them the receiver reads that data off the satellites themselves,
 * so a cold first fix takes 30–90 seconds outdoors, and indoors may never arrive.
 *
 * Three lessons are baked in here, each from a way the previous version failed silently:
 *
 *  - **Permission decides which providers are legal.** Requesting FINE when the manifest
 *    also declares COARSE lets the user grant "Approximate" only. `GPS_PROVIDER` then
 *    throws SecurityException. We check first and register what we are actually allowed
 *    to use, rather than throwing and pretending to search.
 *  - **Register every usable provider.** GPS alone means no fix indoors, ever. FUSED and
 *    NETWORK give a real, live, accuracy-tagged fix; we keep the best one we have seen.
 *  - **Say what is happening.** Satellite counts come from [GnssStatus], so "searching"
 *    can be distinguished from "dead".
 */
@SuppressLint("MissingPermission")
class LocationProvider(context: Context) {

    private val appContext = context.applicationContext
    private val lm = appContext.getSystemService(Context.LOCATION_SERVICE) as LocationManager

    private val listeners = mutableListOf<Pair<String, LocationListener>>()
    private var gnssCallback: GnssStatus.Callback? = null
    private var best: Location? = null
    private var activeFixSignal: CancellationSignal? = null

    fun hasFineLocation(): Boolean = granted(Manifest.permission.ACCESS_FINE_LOCATION)
    fun hasCoarseLocation(): Boolean = granted(Manifest.permission.ACCESS_COARSE_LOCATION)
    fun isLocationEnabled(): Boolean = lm.isLocationEnabled
    fun hasGps(): Boolean = lm.allProviders.contains(LocationManager.GPS_PROVIDER)

    private fun granted(p: String) =
        ContextCompat.checkSelfPermission(appContext, p) == PackageManager.PERMISSION_GRANTED

    /**
     * Subscribe until [stop]. [onFix] fires with the best fix seen so far; [onStatus]
     * narrates progress so the UI never has to guess. Idempotent.
     *
     * @return the providers we successfully registered — empty means no location is coming.
     */
    fun start(onFix: (Location) -> Unit, onStatus: (String) -> Unit): List<String> {
        if (listeners.isNotEmpty()) return listeners.map { it.first }

        // GPS_PROVIDER requires FINE. With an "Approximate" grant it throws, so do not ask.
        val wanted = buildList {
            if (hasFineLocation()) {
                add(LocationManager.GPS_PROVIDER)
                add(LocationManager.FUSED_PROVIDER)
            }
            if (hasFineLocation() || hasCoarseLocation()) {
                add(LocationManager.NETWORK_PROVIDER)
            }
        }.filter { lm.allProviders.contains(it) }

        for (provider in wanted) {
            val l = LocationListener { loc -> accept(loc, onFix, onStatus) }
            try {
                lm.requestLocationUpdates(provider, MIN_INTERVAL_MS, MIN_DISTANCE_M, l, appContext.mainLooper)
                listeners += provider to l
                Log.i(TAG, "listening on $provider")
            } catch (e: SecurityException) {
                Log.w(TAG, "not permitted to use $provider: ${e.message}")
            } catch (e: Exception) {
                Log.w(TAG, "could not use $provider: ${e.message}")
            }
        }

        if (listeners.isEmpty()) {
            Log.w(TAG, "no usable location provider (fine=${hasFineLocation()} coarse=${hasCoarseLocation()})")
            return emptyList()
        }

        // Seed from the freshest last-known fix so a warm phone shows a position at once.
        bestLastKnown()?.let { accept(it, onFix, onStatus) }

        if (hasFineLocation()) {
            startGnssStatus(onStatus)
            // Airplane mode strips A-GPS, so a cold receiver has to read the almanac off the
            // satellites — slow. Two things speed it up as much as an app is allowed to:
            //  - nudge the chipset to (re)inject whatever predicted-orbit data it has cached,
            //  - actively power a one-shot fix instead of only listening passively.
            nudgeAssistedData()
            requestActiveFix(onFix, onStatus)
        }
        return listeners.map { it.first }
    }

    /**
     * Force the GNSS receiver to actively pursue a single fresh fix, rather than waiting for
     * a passive update that may never come until something else wakes the chipset. This is
     * the biggest lever on airplane-mode first-fix time. API 30+; minSdk is 31.
     */
    private fun requestActiveFix(onFix: (Location) -> Unit, onStatus: (String) -> Unit) {
        if (!hasFineLocation()) return
        activeFixSignal?.cancel()
        val signal = CancellationSignal()
        activeFixSignal = signal
        try {
            lm.getCurrentLocation(
                LocationManager.GPS_PROVIDER,
                signal,
                appContext.mainExecutor
            ) { loc -> if (loc != null) accept(loc, onFix, onStatus) }
        } catch (e: Exception) {
            Log.w(TAG, "active fix request failed: ${e.message}")
        }
    }

    /**
     * Best-effort: ask the GNSS HAL to inject any cached predicted-orbit (PSDS/XTRA) and time
     * data. Without a network it cannot download fresh data, but injecting what is already
     * cached can turn a cold start into a warm one. Unsupported on some chipsets — hence the
     * quiet catch. Command names are the ones documented for the platform GNSS provider.
     */
    private fun nudgeAssistedData() {
        for (cmd in listOf("force_psds_injection", "force_xtra_injection", "force_time_injection")) {
            try {
                lm.sendExtraCommand(LocationManager.GPS_PROVIDER, cmd, null)
            } catch (e: Exception) {
                Log.w(TAG, "GNSS command $cmd unavailable: ${e.message}")
            }
        }
    }

    /** Satellite counts, so "searching" is visibly different from "nothing is happening". */
    private fun startGnssStatus(onStatus: (String) -> Unit) {
        val cb = object : GnssStatus.Callback() {
            override fun onSatelliteStatusChanged(status: GnssStatus) {
                var used = 0
                for (i in 0 until status.satelliteCount) if (status.usedInFix(i)) used++
                if (best == null) {
                    onStatus(
                        when {
                            status.satelliteCount == 0 ->
                                "Searching for satellites — step outside with a clear view of the sky"
                            used >= 4 ->
                                "Locking on — hold still for a moment"
                            else ->
                                "Acquiring GPS — ${status.satelliteCount} satellites in view. " +
                                    "In airplane mode the first fix can take a minute outdoors; keep " +
                                    "the sky in view."
                        }
                    )
                }
            }
        }
        try {
            lm.registerGnssStatusCallback(appContext.mainExecutor, cb)
            gnssCallback = cb
        } catch (e: Exception) {
            Log.w(TAG, "GNSS status unavailable: ${e.message}")
        }
    }

    private fun accept(loc: Location, onFix: (Location) -> Unit, onStatus: (String) -> Unit) {
        if (!isBetter(loc, best)) return
        best = loc
        Log.i(TAG, "fix from ${loc.provider}: ${loc.latitude},${loc.longitude} ±${loc.accuracy}m")
        onFix(loc)
        onStatus("Locked on via ${sourceName(loc.provider)} — accurate to about ${loc.accuracy.toInt()} m")
    }

    private fun sourceName(provider: String?): String = when (provider) {
        LocationManager.GPS_PROVIDER -> "GPS"
        LocationManager.NETWORK_PROVIDER -> "network"
        LocationManager.FUSED_PROVIDER -> "the fused provider"
        else -> provider ?: "an unknown source"
    }

    fun stop() {
        listeners.forEach { (_, l) ->
            try { lm.removeUpdates(l) } catch (e: Exception) { Log.w(TAG, "removeUpdates: ${e.message}") }
        }
        listeners.clear()
        gnssCallback?.let {
            try { lm.unregisterGnssStatusCallback(it) } catch (e: Exception) { /* already gone */ }
        }
        gnssCallback = null
        activeFixSignal?.let { try { it.cancel() } catch (e: Exception) { /* already done */ } }
        activeFixSignal = null
        best = null
    }

    /** Freshest last-known fix across the providers we may read, if recent enough to mean anything. */
    private fun bestLastKnown(): Location? {
        var found: Location? = null
        for ((provider, _) in listeners) {
            val loc = try { lm.getLastKnownLocation(provider) } catch (e: Exception) { null } ?: continue
            if (System.currentTimeMillis() - loc.time > MAX_SEED_AGE_MS) continue
            if (isBetter(loc, found)) found = loc
        }
        return found
    }

    /**
     * Is [candidate] a better fix than [current]? Adapted from the "Determining location"
     * sample in the Android developer documentation (Apache-2.0).
     */
    private fun isBetter(candidate: Location, current: Location?): Boolean {
        if (current == null) return true

        val timeDelta = candidate.time - current.time
        if (timeDelta > SIGNIFICANT_TIME_MS) return true       // much newer: trust it
        if (timeDelta < -SIGNIFICANT_TIME_MS) return false     // much older: ignore it
        val isNewer = timeDelta > 0

        val accuracyDelta = candidate.accuracy - current.accuracy
        val isMoreAccurate = accuracyDelta < 0
        val isMuchLessAccurate = accuracyDelta > 200f
        val sameProvider = candidate.provider == current.provider

        return when {
            isMoreAccurate -> true
            isNewer && accuracyDelta <= 0f -> true
            isNewer && !isMuchLessAccurate && sameProvider -> true
            else -> false
        }
    }

    private companion object {
        const val TAG = "LocationProvider"
        // 0 = give me every fix the receiver produces. During a cold airplane-mode acquisition
        // we want the very first fix the instant it lands, not a second later.
        const val MIN_INTERVAL_MS = 0L
        const val MIN_DISTANCE_M = 0f
        /** Beyond this, a last-known fix says where you *were*, not where you are. */
        const val MAX_SEED_AGE_MS = 2 * 60 * 1000L
        const val SIGNIFICANT_TIME_MS = 2 * 60 * 1000L
    }
}
