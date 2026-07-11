package com.sankatmochan.mesh.model

import android.util.Log
import org.json.JSONObject
import java.nio.charset.StandardCharsets

/** Kind of envelope travelling across the mesh. */
enum class MsgType { SOS, DELIVERED, ACCEPTED }

/**
 * The compact SOS envelope that crosses the mesh (DESIGN.md §5, text-first).
 *
 * Encoded as small-key JSON and kept under [MAX_BYTES] so it fits a single BLE
 * write with a 247-byte MTU (and, later, a 255-byte LoRa frame). This is the
 * ONE thing that travels between devices - everything else is UI.
 */
data class SosMessage(
    val id: String,            // globally-unique: "<origin>-<seq>"
    val type: MsgType,
    val origin: String,        // short id of the originating node (per-session, for routing)
    val deviceId: String = "", // stable id of the originating device (persists across sessions)
    val refId: String? = null, // for DELIVERED/ACCEPTED: the SOS id being answered
    val urgency: Int = 3,      // 1 (low) .. 5 (critical)
    val category: String = "", // e.g. "flood", "trapped", "medical"
    val locationHint: String = "",
    val gist: String = "",     // short free text
    val lang: String = "en",   // BCP-47-ish: "ta", "hi", "en"
    val lat: Double? = null,   // GPS latitude  (captured on-device, offline)
    val lng: Double? = null,   // GPS longitude
    val ts: Long = 0L,         // epoch millis, stamped by the originator
    val hops: Int = 0          // incremented on each store-and-forward relay
) {
    /** True when this envelope carries a usable GPS fix. */
    val hasLocation: Boolean get() = lat != null && lng != null
    /** UTF-8 JSON bytes, guaranteed <= [MAX_BYTES] (gist is trimmed if needed). */
    fun encode(): ByteArray {
        var trimmedGist = gist
        var bytes = toBytes(trimmedGist)
        // Only the free-text gist is trimmed to fit - never the structured fields.
        while (bytes.size > MAX_BYTES && trimmedGist.isNotEmpty()) {
            trimmedGist = trimmedGist.dropLast((bytes.size - MAX_BYTES).coerceAtLeast(1))
            bytes = toBytes(trimmedGist)
        }
        if (bytes.size > MAX_BYTES) {
            Log.w(TAG, "Envelope $id still ${bytes.size}B after trimming gist")
        }
        return bytes
    }

    private fun toBytes(g: String): ByteArray {
        val o = JSONObject()
        o.put("i", id)
        o.put("t", type.name)
        o.put("o", origin)
        if (deviceId.isNotEmpty()) o.put("d", deviceId)
        refId?.let { o.put("r", it) }
        o.put("u", urgency)
        o.put("c", category)
        o.put("l", locationHint)
        o.put("g", g)
        o.put("ln", lang)
        if (lat != null && lng != null) {
            // A raw Double serialises as "12.959670000000001" - 18 bytes of a 244-byte
            // envelope, all but six of them below the noise floor of any phone's GNSS.
            o.put("la", round6(lat))
            o.put("lo", round6(lng))
        }
        o.put("ts", ts)
        o.put("h", hops)
        return o.toString().toByteArray(StandardCharsets.UTF_8)
    }

    /** Six decimal places ≈ 0.11 m - well inside GNSS accuracy, and it keeps the
     *  envelope a predictable size so gist trimming behaves the same every time. */
    private fun round6(v: Double): Double = Math.round(v * 1_000_000.0) / 1_000_000.0

    companion object {
        private const val TAG = "SosMessage"

        /** ATT payload budget for a 247-byte MTU (247 - 3 bytes ATT header). */
        const val MAX_BYTES = 244

        // Field caps - all incoming mesh data is untrusted (CLAUDE.md #8).
        private const val MAX_ID = 32
        private const val MAX_TEXT = 200

        /**
         * Parse + validate an incoming envelope. Returns null if the bytes are
         * malformed, oversized, or fail range/type checks - the caller drops it.
         * Untrusted input is treated as data only; nothing here is executed.
         */
        fun decode(bytes: ByteArray): SosMessage? {
            if (bytes.isEmpty() || bytes.size > MAX_BYTES + 8) return null // small tolerance
            return try {
                val o = JSONObject(String(bytes, StandardCharsets.UTF_8))
                val id = clean(o.optString("i")).take(MAX_ID)
                val origin = clean(o.optString("o")).take(MAX_ID)
                val typeName = o.optString("t")
                if (id.isBlank() || origin.isBlank()) return null
                val type = MsgType.entries.firstOrNull { it.name == typeName } ?: return null
                SosMessage(
                    id = id,
                    type = type,
                    origin = origin,
                    deviceId = if (o.has("d")) clean(o.optString("d")).take(MAX_ID) else "",
                    refId = if (o.has("r")) clean(o.optString("r")).take(MAX_ID) else null,
                    urgency = o.optInt("u", 3).coerceIn(1, 5),
                    category = clean(o.optString("c")).take(48),
                    locationHint = clean(o.optString("l")).take(64),
                    gist = clean(o.optString("g")).take(MAX_TEXT),
                    lang = clean(o.optString("ln", "en")).take(8),
                    lat = parseCoord(o, "la", -90.0, 90.0),
                    lng = parseCoord(o, "lo", -180.0, 180.0),
                    ts = o.optLong("ts", 0L).coerceAtLeast(0L),
                    hops = o.optInt("h", 0).coerceIn(0, 15)
                )
            } catch (e: Exception) {
                Log.w(TAG, "Dropping malformed envelope: ${e.message}")
                null
            }
        }

        /**
         * Strip control characters (newlines, carriage returns, tabs, escapes, NUL, …) from an
         * untrusted free-text field, collapsing them to spaces. Two reasons (CLAUDE.md #8/#9/#10):
         *  - the mesh event log is a single line per entry, so an embedded '\n' would let a
         *    crafted SOS inject fake log lines a reader can't distinguish from real ones;
         *  - the text is later shown on-screen; keeping it to printable characters means what a
         *    responder reads is exactly what was sent, with no hidden or spoofing control codes.
         * This is data cleaning only - the content is never interpreted as commands.
         */
        private fun clean(s: String): String =
            buildString(s.length) { for (ch in s) append(if (ch.isISOControl()) ' ' else ch) }.trim()

        /** Read a coordinate only if present, finite, and within valid bounds. */
        private fun parseCoord(o: JSONObject, key: String, min: Double, max: Double): Double? {
            if (!o.has(key)) return null
            val v = o.optDouble(key, Double.NaN)
            return if (v.isFinite() && v in min..max) v else null
        }
    }
}
