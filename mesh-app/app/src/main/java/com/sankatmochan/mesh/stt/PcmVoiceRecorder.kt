package com.sankatmochan.mesh.stt

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlin.concurrent.thread

/**
 * Captures raw 16 kHz mono PCM from the mic for on-device STT.
 *
 * This is deliberately separate from [com.sankatmochan.mesh.mesh.VoiceRecorder], which produces
 * tiny AMR-NB clips for relaying over the bandwidth-starved mesh. Here we're feeding a neural
 * model on the same phone, so we want clean float PCM at the model's native rate — no lossy codec.
 *
 * The model window is 15 s (see [MelFrontend.frames]); we cap capture there and drop anything
 * beyond it (an SOS utterance is far shorter). Caller must hold RECORD_AUDIO (already granted for
 * the mesh voice feature).
 */
class PcmVoiceRecorder {

    @Volatile private var record: AudioRecord? = null
    @Volatile private var capturing = false
    private var worker: Thread? = null
    private val buffer = ArrayList<Short>(SAMPLE_RATE * MAX_SECONDS)

    val isRecording: Boolean get() = capturing

    /** Begin capture. Returns false if the mic couldn't be opened (caller shows a soft error). */
    fun start(): Boolean {
        if (capturing) return true
        val minBuf = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL, ENCODING)
        if (minBuf <= 0) {
            Log.w(TAG, "getMinBufferSize returned $minBuf")
            return false
        }
        val readChunk = maxOf(minBuf, SAMPLE_RATE / 10) // ~100 ms reads
        val ar = try {
            @Suppress("MissingPermission") // RECORD_AUDIO is requested before we get here
            AudioRecord(MediaRecorder.AudioSource.MIC, SAMPLE_RATE, CHANNEL, ENCODING, readChunk * 2)
        } catch (e: Exception) {
            Log.w(TAG, "AudioRecord ctor failed: ${e.message}")
            return false
        }
        if (ar.state != AudioRecord.STATE_INITIALIZED) {
            Log.w(TAG, "AudioRecord not initialized")
            runCatching { ar.release() }
            return false
        }
        synchronized(buffer) { buffer.clear() }
        record = ar
        capturing = true
        ar.startRecording()
        val cap = SAMPLE_RATE * MAX_SECONDS
        worker = thread(name = "pcm-capture") {
            val tmp = ShortArray(readChunk)
            while (capturing) {
                val n = ar.read(tmp, 0, tmp.size)
                if (n <= 0) continue
                synchronized(buffer) {
                    var i = 0
                    while (i < n && buffer.size < cap) { buffer.add(tmp[i]); i++ }
                    if (buffer.size >= cap) capturing = false // hit the 15 s cap → stop
                }
            }
        }
        return true
    }

    /**
     * Stop capture and return the recording as mono float32 in [-1, 1], or null if nothing usable
     * was captured (too short / mic error). Safe to call even if not recording.
     */
    suspend fun stop(): FloatArray? = withContext(Dispatchers.IO) {
        if (record == null) return@withContext null
        capturing = false
        runCatching { worker?.join(500) }
        val ar = record
        record = null
        runCatching { ar?.stop() }
        runCatching { ar?.release() }
        val pcm = synchronized(buffer) { buffer.toShortArray() }
        if (pcm.size < SAMPLE_RATE / 2) return@withContext null // < 0.5 s → treat as no speech
        FloatArray(pcm.size) { pcm[it] / 32768f }
    }

    /** Abort capture and discard audio (e.g. user cancels). */
    fun cancel() {
        capturing = false
        runCatching { worker?.join(300) }
        val ar = record
        record = null
        runCatching { ar?.stop() }
        runCatching { ar?.release() }
        synchronized(buffer) { buffer.clear() }
    }

    private companion object {
        const val TAG = "PcmVoiceRecorder"
        const val SAMPLE_RATE = 16_000
        const val CHANNEL = AudioFormat.CHANNEL_IN_MONO
        const val ENCODING = AudioFormat.ENCODING_PCM_16BIT
        const val MAX_SECONDS = 15 // matches MelFrontend.frames (1501 frames @ 10 ms)
    }
}
