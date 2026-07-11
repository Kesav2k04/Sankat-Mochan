package com.sankatmochan.mesh.stt

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.content.Context
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.File
import java.nio.FloatBuffer
import java.nio.IntBuffer

/**
 * On-device speech-to-text for the OnePlus 15 (Snapdragon 8 Elite Gen 5), behind one class
 * so the rest of the app never imports `ai.onnxruntime.*` and there's a single place to review
 * the AI runtime (mirrors [com.sankatmochan.mesh.chat.GenieXEngine] — CLAUDE.md #5/#6).
 *
 * Pipeline (all offline):
 *   PCM 16 kHz ─▶ [MelFrontend] (1,80,1501) ─▶ encoder QNN graph ─▶ (1,1024,188)
 *              ─▶ ctc_decoder QNN graph ─▶ (1,188,5633) ─▶ [CtcDecoder] ─▶ text
 *
 * The two heavy graphs run on the Hexagon NPU via ONNX Runtime's QNN execution provider.
 * They are AI Hub `precompiled_qnn_onnx` artifacts: a small model.onnx wrapper (EPContext node)
 * that references a sibling QNN context binary (model.bin). ORT-QNN loads the wrapper and executes
 * the .bin on the NPU. Both files sit together in a per-graph folder (the EPContext path is
 * relative); the ~1.2 GB encoder is side-loaded (see modelDir), not bundled in the APK.
 *
 * ── INTEGRATION STATUS ─────────────────────────────────────────────────────────────────────
 * Done: mel parity VERIFIED (MelFrontend matches the NeMo preprocessor to ~8e-5; androidTest
 * MelParityTest guards it), language auto-detected from the CTC logits (CtcDecoder.pickLanguage,
 * 100% on FLEURS — no separate SLID model), encoder length-masking wired via encoded_lengths.
 * Remaining, only verifiable on the phone (see stt/README.md):
 *   (B) libQnnHtp.so must load for ORT. GenieX already ships QAIRT libs; confirm the ORT-QNN AAR's
 *       QAIRT version and GenieX's don't clash in the same APK. Until confirmed, test STT with the
 *       assistant LLM unloaded.
 *   (C) Confirm tensor IO names/dtypes on-device (audio_signal/length → outputs/encoded_lengths;
 *       encoder_output → logprobs). --truncate_64bit_io was used, so length/encoded_lengths may be
 *       int32 at the QNN boundary (readLength handles both).
 */
class SttEngine(context: Context) {

    private val appContext = context.applicationContext
    private val lock = Mutex()
    private val env: OrtEnvironment by lazy { OrtEnvironment.getEnvironment() }

    private var mel: MelFrontend? = null
    private var ctc: CtcDecoder? = null
    private var encoderSession: OrtSession? = null
    private var ctcSession: OrtSession? = null

    /**
     * Where the (large) QNN model files live. The encoder context binary is ~1.2 GB (float), far
     * too big to ship in the APK — so it's side-loaded, exactly like the GenieX LLM weights.
     *
     * Layout (each AI Hub precompiled_qnn_onnx graph is a folder of model.onnx + model.bin; the
     * EPContext .onnx references its .bin by RELATIVE name, so the two must stay together and keep
     * their names — hence a subdir per graph):
     *   files/stt/encoder/model.onnx      + files/stt/encoder/model.bin
     *   files/stt/ctc_decoder/model.onnx  + files/stt/ctc_decoder/model.bin
     * Pushed with tools/push_stt_model.sh (see stt/README.md). vocab.json + language_masks.json
     * are small and ship in assets.
     */
    val modelDir: File = File(appContext.getExternalFilesDir(null), "stt")

    private val encoderOnnx: File get() = File(modelDir, "encoder/model.onnx")
    private val ctcOnnx: File get() = File(modelDir, "ctc_decoder/model.onnx")
    private val modelFiles get() = listOf(
        encoderOnnx, File(modelDir, "encoder/model.bin"),
        ctcOnnx, File(modelDir, "ctc_decoder/model.bin"),
    )

    init {
        // Create the per-graph dirs as the APP (owner) so files pushed via `adb push` land in an
        // app-readable dir. Dirs created by the adb shell under Android/data/<pkg> are owned by
        // `shell` with no world-traverse bit, so the app can't read files inside them — the model
        // must be pushed into app-created dirs (same pattern GenieX uses for its GGUF weights).
        runCatching { File(modelDir, "encoder").mkdirs(); File(modelDir, "ctc_decoder").mkdirs() }
    }

    val isLoaded: Boolean get() = encoderSession != null && ctcSession != null

    /** True once all model files are present on disk (pushed/downloaded). Cheap to poll. */
    fun modelsInstalled(): Boolean = modelFiles.all { it.exists() && it.length() > 0 }

    sealed interface LoadResult {
        data object Ok : LoadResult
        /** Device/build can't run QNN, or assets are missing. [message] is user-safe. */
        data class Failed(val message: String) : LoadResult
    }

    /** Sealed result so callers never see a raw exception/stack trace (CLAUDE.md #10). */
    sealed interface SttResult {
        data class Ok(val text: String, val lang: String, val latencyMs: Long) : SttResult
        data object Failed : SttResult
    }

    /** Load both QNN graphs + the decoder assets. Idempotent. */
    suspend fun load(): LoadResult = lock.withLock {
        if (isLoaded) return@withLock LoadResult.Ok
        if (!modelsInstalled()) {
            return@withLock LoadResult.Failed("Speech model isn't installed on this phone yet.")
        }
        withContext(Dispatchers.IO) {
            runCatching {
                // The EPContext .onnx references its .bin by relative name, so each graph loads
                // from its own folder where model.onnx + model.bin sit together (see modelDir).
                encoderSession = env.createSession(encoderOnnx.absolutePath, qnnOptions())
                ctcSession = env.createSession(ctcOnnx.absolutePath, qnnOptions())
                ctc = CtcDecoder.fromAssets(appContext)  // vocab.json + language_masks.json (small)
                mel = MelFrontend.fromAssets(appContext) // mel_window512.f32 + mel_fb.f32 (bundled)
                LoadResult.Ok as LoadResult
            }.getOrElse { e ->
                Log.e(TAG, "STT load failed", e)   // detail to Logcat only (CLAUDE.md #10)
                unloadInternal()
                LoadResult.Failed("On-device transcription isn't available on this device.")
            }
        }
    }

    private fun qnnOptions(): OrtSession.SessionOptions = OrtSession.SessionOptions().apply {
        // QNN EP → Hexagon NPU. backend_path resolves via the app's native lib dir / LD_LIBRARY_PATH.
        addQnn(
            mapOf(
                "backend_path" to "libQnnHtp.so",
                "htp_performance_mode" to "burst",
                "qnn_context_priority" to "high",
            )
        )
    }

    /**
     * Transcribe one clip. If [lang] is null the language is auto-detected from the CTC logits
     * (the encoder is language-agnostic — see [CtcDecoder.pickLanguage]); pass a code to force it.
     * Never throws to the caller.
     */
    suspend fun transcribe(pcm16k: FloatArray, lang: String? = null): SttResult =
        withContext(Dispatchers.IO) {
            val enc = encoderSession
            val dec = ctcSession
            val decoder = ctc
            val front = mel
            if (enc == null || dec == null || decoder == null || front == null) return@withContext SttResult.Failed
            if (lang != null && lang !in decoder.supportedLanguages) return@withContext SttResult.Failed

            val t0 = System.nanoTime()
            runCatching {
                val feats = front.logMel(pcm16k)
                val audioTensor = OnnxTensor.createTensor(
                    env, FloatBuffer.wrap(feats.data),
                    longArrayOf(1, front.nMels.toLong(), front.frames.toLong()),
                )
                // Pass the clip's REAL frame count so the encoder masks the zero-padded tail.
                // int32: the encoder was compiled with --truncate_64bit_io, so `length` is int32.
                val lenTensor = OnnxTensor.createTensor(
                    env, IntBuffer.wrap(intArrayOf(feats.validFrames)), longArrayOf(1),
                )
                val encOut = enc.run(mapOf("audio_signal" to audioTensor, "length" to lenTensor))
                val encoderOutput = encOut.tensor(ENC_OUT)                  // (1,1024,188)
                val validOut = readLength(encOut, ENC_LEN)                   // valid output frames

                val ctcOut = dec.run(mapOf(CTC_IN to encoderOutput))
                val logprobsT = ctcOut.tensor(CTC_OUT)                      // (1,T,5633)
                val outFrames = logprobsT.info.shape[1].toInt()
                val frames = if (validOut in 1..outFrames) validOut else outFrames
                val logprobs = (logprobsT.value as? FloatArray) ?: flatten(logprobsT)

                val chosen = lang ?: decoder.pickLanguage(logprobs, frames)
                val text = decoder.decode(logprobs, frames, chosen)
                audioTensor.close(); lenTensor.close(); encOut.close(); ctcOut.close()
                SttResult.Ok(text, chosen, (System.nanoTime() - t0) / 1_000_000) as SttResult
            }.getOrElse { e ->
                Log.e(TAG, "transcription failed", e)   // CLAUDE.md #10
                SttResult.Failed
            }
        }

    /** OrtSession.Result.get(name) returns Optional<OnnxValue> — unwrap to the tensor. */
    private fun OrtSession.Result.tensor(name: String): OnnxTensor =
        this.get(name).orElseThrow { IllegalStateException("missing output '$name'") } as OnnxTensor

    /** encoded_lengths is int64, or int32 after --truncate_64bit_io. Read either → Int. */
    private fun readLength(res: OrtSession.Result, name: String): Int = runCatching {
        when (val v = res.tensor(name).value) {
            is LongArray -> v[0].toInt()
            is IntArray -> v[0]
            else -> -1
        }
    }.getOrDefault(-1)

    /** ORT hands back nested float arrays for >1-D outputs; flatten (1,T,5633) → FloatArray. */
    private fun flatten(t: OnnxTensor): FloatArray {
        @Suppress("UNCHECKED_CAST")
        val a = t.value as Array<Array<FloatArray>>   // [1][T][5633]
        val batch = a[0]
        val out = FloatArray(batch.size * CtcDecoder.VOCAB_CLASSES)
        for (i in batch.indices) System.arraycopy(batch[i], 0, out, i * CtcDecoder.VOCAB_CLASSES, batch[i].size)
        return out
    }

    suspend fun unload() = lock.withLock { withContext(Dispatchers.IO) { unloadInternal() } }

    private fun unloadInternal() {
        runCatching { encoderSession?.close() }
        runCatching { ctcSession?.close() }
        encoderSession = null; ctcSession = null; ctc = null
    }

    private companion object {
        const val TAG = "SttEngine"
        // IO names in the AI-Hub-compiled wrappers. Inputs keep their names (audio_signal, length,
        // encoder_output) but outputs are renamed generically: encoder → output_0 (features),
        // output_1 (encoded_lengths); ctc_decoder → output_0 (logprobs). Verified from the onnx.
        const val ENC_OUT = "output_0"
        const val ENC_LEN = "output_1"
        const val CTC_IN = "encoder_output"
        const val CTC_OUT = "output_0"
    }
}
