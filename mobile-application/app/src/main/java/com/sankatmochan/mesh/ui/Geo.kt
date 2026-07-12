package com.sankatmochan.mesh.ui

import android.location.Location

/**
 * Distance and bearing between two fixes. Uses the framework's own WGS-84 solver
 * rather than a hand-rolled haversine, so the numbers a rescuer walks on agree with
 * every other tool on the phone.
 */
object Geo {

    /** Metres between two points. */
    fun distanceMeters(fromLat: Double, fromLng: Double, toLat: Double, toLng: Double): Float {
        val out = FloatArray(2)
        Location.distanceBetween(fromLat, fromLng, toLat, toLng, out)
        return out[0]
    }

    /** Initial bearing from the first point to the second, normalised to 0..360. */
    fun bearingDegrees(fromLat: Double, fromLng: Double, toLat: Double, toLng: Double): Float {
        val out = FloatArray(2)
        Location.distanceBetween(fromLat, fromLng, toLat, toLng, out)
        return (out[1] + 360f) % 360f
    }

    /** "NE", "SSW" - a direction a person can act on without reading a number. */
    fun compassPoint(bearing: Float): String {
        val points = arrayOf(
            "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
        )
        val i = Math.round(bearing / 22.5f) % 16
        return points[i]
    }

    /** "420 m" / "1.4 km" - metres below a kilometre, where precision still matters. */
    fun formatDistance(meters: Float): String =
        if (meters < 1000f) "${Math.round(meters)} m"
        else "%.1f km".format(meters / 1000f)

    /** "420 m NE", or null when we do not know where the rescuer is. */
    fun describeRoute(
        meLat: Double?, meLng: Double?, toLat: Double?, toLng: Double?
    ): String? {
        if (meLat == null || meLng == null || toLat == null || toLng == null) return null
        val d = distanceMeters(meLat, meLng, toLat, toLng)
        val b = bearingDegrees(meLat, meLng, toLat, toLng)
        return "${formatDistance(d)} ${compassPoint(b)}"
    }
}
