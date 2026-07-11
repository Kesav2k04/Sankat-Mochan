package com.sankatmochan.mesh.mesh

import android.content.Context
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject

/**
 * A single fixed point on the offline map: either a general landmark for orientation, or a
 * designated **reunion / muster point** where people are directed to gather and be safe.
 *
 * These are read from a bundled asset ([SafePoints]) rather than fetched over the network —
 * the whole app is offline-first, so map context has to travel inside the APK. Every field is
 * treated as untrusted data even though it ships with the build (CLAUDE.md #8): coordinates
 * are range-checked and the human-readable strings are only ever rendered as plain text
 * (CLAUDE.md #9), never as markup.
 */
data class MapPoint(
    val name: String,
    val lat: Double,
    val lng: Double,
    val kind: Kind,
    val detail: String = "",
) {
    enum class Kind { LANDMARK, REUNION }
}

object SafePoints {
    private const val TAG = "SafePoints"
    private const val ASSET = "safe_points.json"

    @Volatile
    private var cache: List<MapPoint>? = null

    /** All points, parsed once and cached. Empty list if the asset is missing or unreadable —
     *  a missing dataset must never take the map down. */
    fun all(context: Context): List<MapPoint> {
        cache?.let { return it }
        val loaded = runCatching { load(context) }.getOrElse {
            Log.w(TAG, "could not read $ASSET: ${it.message}")
            emptyList()
        }
        cache = loaded
        return loaded
    }

    fun reunions(context: Context): List<MapPoint> =
        all(context).filter { it.kind == MapPoint.Kind.REUNION }

    fun landmarks(context: Context): List<MapPoint> =
        all(context).filter { it.kind == MapPoint.Kind.LANDMARK }

    private fun load(context: Context): List<MapPoint> {
        val json = context.assets.open(ASSET).bufferedReader().use { it.readText() }
        val root = JSONObject(json)
        val out = ArrayList<MapPoint>()
        parseArray(root.optJSONArray("landmarks"), MapPoint.Kind.LANDMARK, out)
        parseArray(root.optJSONArray("reunionPoints"), MapPoint.Kind.REUNION, out)
        return out
    }

    private fun parseArray(arr: JSONArray?, kind: MapPoint.Kind, out: MutableList<MapPoint>) {
        if (arr == null) return
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            val lat = o.optDouble("lat", Double.NaN)
            val lng = o.optDouble("lng", Double.NaN)
            // Reject anything that isn't a real coordinate before it ever reaches the map.
            if (lat.isNaN() || lng.isNaN() || lat !in -90.0..90.0 || lng !in -180.0..180.0) continue
            val name = o.optString("name").trim().take(60)
            if (name.isEmpty()) continue
            out.add(MapPoint(name, lat, lng, kind, o.optString("detail").trim().take(80)))
        }
    }
}
