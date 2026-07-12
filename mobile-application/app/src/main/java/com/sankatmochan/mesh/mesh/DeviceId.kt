package com.sankatmochan.mesh.mesh

import android.content.Context
import android.provider.Settings
import android.util.Log
import java.security.MessageDigest
import java.util.UUID

/**
 * A stable, unique identifier for this physical Android device.
 *
 * Unlike [BleMeshService.nodeId] (a fresh random id every app session, used so message ids
 * never collide across restarts), this id is generated once and persisted, so the SAME phone
 * keeps the SAME device id across restarts. It rides along in every SOS envelope so a control
 * room can tell "which handset raised this" even after the sender's session id has rolled over.
 *
 * We derive it from a seed and store the short, hashed result - never the raw seed. The seed is
 * ANDROID_ID when available (stable per device + app signing key, no permission required), with a
 * random UUID fallback for the rare device that reports the known-buggy emulator value or none at
 * all. Because we ship only the SHA-256-derived 12 hex chars, the raw ANDROID_ID never leaves the
 * phone. Persisted in a private SharedPreferences file (flagged for review per CLAUDE.md #6:
 * this is device-storage handling).
 */
object DeviceId {

    private const val TAG = "DeviceId"
    private const val PREFS = "device_identity"
    private const val KEY = "device_id"
    /** A known-buggy ANDROID_ID shared by a batch of early emulators/devices. */
    private const val BAD_ANDROID_ID = "9774d56d682e549c"
    /** 12 hex chars: stable, collision-safe for a mesh, and small on a 244-byte envelope. */
    private const val LENGTH = 12

    @Volatile private var cached: String? = null

    /** The device id, generating and persisting it on first use. Cheap after the first call. */
    fun get(context: Context): String {
        cached?.let { return it }
        synchronized(this) {
            cached?.let { return it }
            val prefs = context.applicationContext
                .getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            val existing = prefs.getString(KEY, null)
            val id = if (!existing.isNullOrBlank()) {
                existing
            } else {
                deriveId(context).also { prefs.edit().putString(KEY, it).apply() }
            }
            cached = id
            return id
        }
    }

    private fun deriveId(context: Context): String {
        val seed = try {
            Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID)
        } catch (e: Exception) {
            Log.w(TAG, "ANDROID_ID unavailable, using random seed: ${e.message}")
            null
        }
        val usable = if (!seed.isNullOrBlank() && seed != BAD_ANDROID_ID) {
            seed
        } else {
            UUID.randomUUID().toString()
        }
        val digest = MessageDigest.getInstance("SHA-256").digest(usable.toByteArray())
        return buildString(LENGTH) {
            for (b in digest) {
                if (length >= LENGTH) break
                append("%02x".format(b))
            }
        }.take(LENGTH)
    }
}
