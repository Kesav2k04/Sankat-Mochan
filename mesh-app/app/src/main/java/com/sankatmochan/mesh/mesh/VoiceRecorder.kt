package com.sankatmochan.mesh.mesh

import android.content.Context
import android.media.MediaRecorder
import android.util.Log
import java.io.File

/**
 * Records a short Ogg/Opus clip with the platform encoder — no third-party codec, so no
 * new dependency and no licence to honour (Codec2, the obvious alternative at 700 bps,
 * is LGPL-2.1 and outside CLAUDE.md #1's allowlist).
 *
 * Opus cannot go below about 6 kbps, and every one of those bits has to cross a LoRa
 * channel that carries roughly 5 kbps. So the clip length is capped hard: at 6 kbps a
 * 5-second clip is ~3.7 kB, which is 22 frames and about 7 seconds of airtime at SF7.
 * Double the length and you double the time the channel is unavailable to everyone else.
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
        val out = File(dir, "outgoing.ogg")
        out.delete()

        val r = MediaRecorder(appContext)
        return try {
            r.setAudioSource(MediaRecorder.AudioSource.MIC)
            r.setOutputFormat(MediaRecorder.OutputFormat.OGG)
            r.setAudioEncoder(MediaRecorder.AudioEncoder.OPUS)
            r.setAudioChannels(1)
            r.setAudioSamplingRate(16_000)
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
        Log.i(TAG, "recorded ${bytes.size} bytes of Ogg/Opus")
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
        /** Opus' practical floor. Anything higher buys quality nobody can afford on air. */
        const val BITRATE_BPS = 6_000
        const val MAX_MILLIS = 5_000
    }
}
