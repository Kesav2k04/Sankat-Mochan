package com.sankatmochan.mesh.mesh

import android.content.Context
import android.media.MediaRecorder
import com.sankatmochan.mesh.model.VoiceChunk
import android.util.Log
import java.io.File

/**
 * Records a short AMR-NB clip with the platform encoder — no third-party codec, so no new
 * dependency. (Codec2, the obvious alternative at 700 bps, is LGPL-2.1 and outside
 * CLAUDE.md #1's allowlist. AMR-NB is patent-encumbered, but we are calling the OS codec
 * the device vendor already licensed, not shipping one — flagged for review per #6.)
 *
 * Why not Opus: MediaRecorder ignores setAudioEncodingBitRate for OPUS on most devices.
 * A 5-second clip measured ~9 kB (≈14 kbps) — 45 LoRa frames, over 15 seconds of airtime
 * at SF7, during which nobody else's SOS can get through. AMR-NB honours 4.75 kbps, so the
 * same 5 seconds is ~3 kB: about 16 frames and 5.5 seconds of air.
 *
 * Every bit here crosses a channel that carries roughly 5 kbps, so the length is capped
 * hard. Double the clip and you double the time the channel is unavailable to everyone.
 */
class VoiceRecorder(context: Context) {

    private val appContext = context.applicationContext
    private var recorder: MediaRecorder? = null
    private var target: File? = null

    val isRecording: Boolean get() = recorder != null

    /** Begin recording. Returns false if the microphone could not be opened. */
    fun start(): Boolean {
        if (recorder != null) return true
        val dir = File(appContext.filesDir, "voice").apply { mkdirs() }
        val out = File(dir, "outgoing.3gp")
        out.delete()

        val r = MediaRecorder(appContext)
        return try {
            r.setAudioSource(MediaRecorder.AudioSource.MIC)
            r.setOutputFormat(MediaRecorder.OutputFormat.THREE_GPP)
            r.setAudioEncoder(MediaRecorder.AudioEncoder.AMR_NB)
            r.setAudioChannels(1)
            r.setAudioSamplingRate(8_000)          // AMR-NB is defined only at 8 kHz
            r.setAudioEncodingBitRate(BITRATE_BPS)
            r.setMaxDuration(MAX_MILLIS)          // backstop; the UI stops us first
            r.setOutputFile(out.absolutePath)
            r.prepare()
            r.start()
            recorder = r
            target = out
            true
        } catch (e: Exception) {
            Log.w(TAG, "could not start recording: ${e.message}")
            runCatching { r.release() }
            recorder = null
            target = null
            false
        }
    }

    /** Stop and return the encoded clip, or null if nothing usable was captured. */
    fun stop(): ByteArray? {
        val r = recorder ?: return null
        recorder = null
        val out = target
        target = null
        try {
            r.stop()
        } catch (e: Exception) {
            // stop() throws when the clip is too short to produce a valid container.
            Log.w(TAG, "recording too short or failed: ${e.message}")
            runCatching { r.release() }
            out?.delete()
            return null
        }
        runCatching { r.release() }

        val bytes = try {
            out?.readBytes()
        } catch (e: Exception) {
            Log.w(TAG, "could not read clip: ${e.message}")
            null
        }
        out?.delete()
        if (bytes == null || bytes.isEmpty()) return null
        Log.i(TAG, "recorded ${bytes.size} bytes of AMR-NB")
        return bytes
    }

    fun cancel() {
        val r = recorder ?: return
        recorder = null
        runCatching { r.stop() }
        runCatching { r.release() }
        target?.delete()
        target = null
    }

    companion object {
        private const val TAG = "VoiceRecorder"
        /** AMR-NB's lowest mode. Anything higher buys quality nobody can afford on air. */
        const val BITRATE_BPS = 4_750
        const val MAX_MILLIS = 5_000
        /** Wire codec id these clips carry. */
        const val CODEC = VoiceChunk.CODEC_3GPP_AMR
    }
}
