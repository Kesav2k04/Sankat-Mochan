package com.sankatmochan.mesh.mesh

import android.content.Context
import android.util.Log
import com.sankatmochan.mesh.model.VoiceChunk
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import java.io.File

/** A voice message being reassembled, or finished and ready to play. */
data class VoiceClip(
    val clipId: String,
    val origin: String,
    val total: Int,
    val received: Int,
    val hops: Int,
    val codec: Int,
    val file: File?,          // non-null once every chunk has arrived
) {
    val complete: Boolean get() = file != null
    val missing: Int get() = total - received
}

/**
 * Reassembles voice clips arriving chunk by chunk, in any order, possibly duplicated by
 * the mesh's store-and-forward.
 *
 * The one invariant: **a clip is never playable until every chunk is present.** There is
 * no acknowledgement or retransmission on the LoRa link today, so losing one frame of an
 * Ogg stream corrupts the container. Better to show "19 of 22 pieces" than to hand
 * MediaPlayer a truncated file and let it fail in front of a rescuer.
 */
class VoiceClipStore(context: Context) {

    private val dir = File(context.applicationContext.filesDir, "voice").apply { mkdirs() }
    private val parts = HashMap<String, Array<ByteArray?>>()

    private val _clips = MutableStateFlow<List<VoiceClip>>(emptyList())
    val clips: StateFlow<List<VoiceClip>> = _clips.asStateFlow()

    /** Feed one chunk in. Safe to call from the BLE binder threads. */
    @Synchronized
    fun accept(chunk: VoiceChunk) {
        val slots = parts.getOrPut(chunk.clipId) {
            if (parts.size >= MAX_CLIPS_IN_FLIGHT) evictOldest()
            arrayOfNulls(chunk.total)
        }
        // A second chunk claiming a different total is either corruption or a collision
        // between two clips with the same id. Drop it rather than resize and misassemble.
        if (slots.size != chunk.total) {
            Log.w(TAG, "chunk ${chunk.id} says total=${chunk.total}, expected ${slots.size}")
            return
        }
        if (chunk.index >= slots.size) return          // already range-checked in decode()
        slots[chunk.index] = chunk.payload

        val received = slots.count { it != null }
        var file: File? = null
        if (received == slots.size) {
            file = writeClip(chunk.clipId, chunk.codec, slots)
            if (file != null) parts.remove(chunk.clipId)
        }
        publish(chunk, received, file)
    }

    private fun writeClip(clipId: String, codec: Int, slots: Array<ByteArray?>): File? = try {
        // MediaPlayer sniffs the container, but a correct suffix keeps it honest.
        val out = File(dir, clipId + VoiceChunk.extensionFor(codec))
        out.outputStream().use { s -> slots.forEach { s.write(it!!) } }
        Log.i(TAG, "clip $clipId complete: ${out.length()} bytes")
        out
    } catch (e: Exception) {
        Log.w(TAG, "could not write clip $clipId: ${e.message}")
        null
    }

    private fun publish(chunk: VoiceChunk, received: Int, file: File?) {
        _clips.update { current ->
            val existing = current.firstOrNull { it.clipId == chunk.clipId }
            val updated = VoiceClip(
                clipId = chunk.clipId,
                origin = chunk.origin,
                total = chunk.total,
                received = received,
                hops = maxOf(existing?.hops ?: 0, chunk.hops),
                codec = chunk.codec,
                file = file ?: existing?.file,
            )
            (current.filterNot { it.clipId == chunk.clipId } + updated)
                .sortedByDescending { it.clipId }
        }
    }

    /** Bound memory: a stalled clip must not pin 100 kB forever. */
    private fun evictOldest() {
        val victim = parts.keys.firstOrNull() ?: return
        parts.remove(victim)
        Log.w(TAG, "evicted incomplete clip $victim to bound memory")
    }

    private companion object {
        const val TAG = "VoiceClipStore"
        const val MAX_CLIPS_IN_FLIGHT = 8
    }
}
