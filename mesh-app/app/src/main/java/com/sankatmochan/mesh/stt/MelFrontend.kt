package com.sankatmochan.mesh.stt

import android.content.Context
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.ln
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Log-mel front-end for IndicConformer, a bit-for-bit port of the model's own NeMo
 * `preprocessor.ts` (AI4Bharat, MIT). VERIFIED: `command-post/dump_mel_golden.py`
 * reconstructs this exact algorithm in Python and matches the scripted preprocessor to
 * max-abs-diff ≈ 8e-5 on fleurs/hi_0.wav. The 512-pt window and 257×80 mel filterbank are
 * the model's real constants, shipped as assets (`mel_window512.f32`, `mel_fb.f32`), so the
 * only thing that can drift is arithmetic - which the androidTest golden check guards.
 *
 * Pipeline (all constants pulled from preprocessor.ts):
 *   1. global pre-emphasis: y[t] = x[t] − 0.97·x[t−1]
 *   2. reflect-pad 256 samples each side (center=false STFT)
 *   3. per frame: y[t·160 : t·160+512] · window512 → 512-pt FFT → power spectrum (257)
 *   4. mel: fb(257×80)ᵀ · power → 80 bins
 *   5. log(x + 5.96e-8)
 *   6. per-feature norm over VALID frames: mean (÷N), var (÷N−1, clamped), (x−mean)/(std+1e-5)
 *
 * Output is (80 × [frames]) row-major; frames beyond the clip's valid length are zeroed and the
 * valid count is returned so the encoder can mask the padding (fixed 15 s / 1501-frame window).
 */
class MelFrontend(
    private val window512: FloatArray,   // 512, centered analysis window (win_length 400)
    private val fb: FloatArray,          // 257*80 row-major mel filterbank
) {
    val nMels = NMEL
    val frames = MAX_FRAMES

    data class Features(val data: FloatArray, val validFrames: Int)

    /**
     * @param pcm mono 16 kHz float samples in [-1, 1].
     * @return [Features]: data = FloatArray(80*1501) row-major (m*1501 + t), plus validFrames
     *   (real frames for this clip; the rest are zero and should be masked via the encoder length).
     */
    fun logMel(pcm: FloatArray): Features {
        val out = FloatArray(NMEL * MAX_FRAMES)
        if (pcm.size < HOP) return Features(out, 1)

        val valid = minOf(MAX_FRAMES, pcm.size / HOP + 1)      // NeMo: floor(len/hop)+1

        // 1. pre-emphasis (global, y[0] = x[0]) then 2. reflect-pad 256 each side.
        val pre = DoubleArray(pcm.size)
        pre[0] = pcm[0].toDouble()
        for (i in 1 until pcm.size) pre[i] = pcm[i].toDouble() - PREEMPH * pcm[i - 1]
        val padded = reflectPad(pre, PAD)

        val re = DoubleArray(NFFT)
        val im = DoubleArray(NFFT)
        val rowMean = DoubleArray(NMEL)
        val rowSumSq = DoubleArray(NMEL)

        for (t in 0 until valid) {
            java.util.Arrays.fill(im, 0.0)
            val base = t * HOP
            for (i in 0 until NFFT) re[i] = padded[base + i] * window512[i]
            fftRadix2(re, im)
            for (m in 0 until NMEL) {
                var e = 0.0
                var k = 0
                while (k <= NFFT / 2) {                          // 257 bins
                    val p = re[k] * re[k] + im[k] * im[k]        // power (mag²)
                    e += fb[k * NMEL + m] * p
                    k++
                }
                val v = ln(e + GUARD)
                out[m * MAX_FRAMES + t] = v.toFloat()
                rowMean[m] += v
                rowSumSq[m] += v * v
            }
        }

        // 6. per-feature normalization over the VALID frames (mean ÷N, var ÷N−1) - matches NeMo.
        val n = valid.toDouble()
        val denom = if (valid > 1) (valid - 1).toDouble() else 1.0
        for (m in 0 until NMEL) {
            val mean = rowMean[m] / n
            var varr = (rowSumSq[m] - n * mean * mean) / denom
            if (varr < GUARD) varr = GUARD                        // torch.clamp(var, 5.96e-8)
            val inv = 1.0 / (sqrt(varr) + STD_EPS)
            val off = m * MAX_FRAMES
            for (t in 0 until valid) out[off + t] = ((out[off + t] - mean) * inv).toFloat()
            // frames >= valid stay 0 (masked by the encoder length).
        }
        return Features(out, valid)
    }

    /** numpy 'reflect' padding: [1,2,3,4] pad2 → [3,2,1,2,3,4,3,2]. Requires len > pad. */
    private fun reflectPad(x: DoubleArray, pad: Int): DoubleArray {
        val n = x.size
        val out = DoubleArray(n + 2 * pad)
        for (k in 0 until pad) out[k] = x[pad - k]               // left: x[pad..1]
        System.arraycopy(x, 0, out, pad, n)
        for (k in 0 until pad) out[n + pad + k] = x[n - 2 - k]   // right: x[n-2..n-1-pad]
        return out
    }

    /** In-place iterative radix-2 Cooley–Tukey FFT (NFFT is a power of two). */
    private fun fftRadix2(re: DoubleArray, im: DoubleArray) {
        val n = re.size
        var j = 0
        for (i in 1 until n) {
            var bit = n shr 1
            while (j and bit != 0) { j = j xor bit; bit = bit shr 1 }
            j = j or bit
            if (i < j) {
                val tr = re[i]; re[i] = re[j]; re[j] = tr
                val ti = im[i]; im[i] = im[j]; im[j] = ti
            }
        }
        var len = 2
        while (len <= n) {
            val ang = -2.0 * PI / len
            val wRe = cos(ang); val wIm = sin(ang)
            var i = 0
            while (i < n) {
                var curRe = 1.0; var curIm = 0.0
                for (k in 0 until len / 2) {
                    val aRe = re[i + k]; val aIm = im[i + k]
                    val bRe = re[i + k + len / 2] * curRe - im[i + k + len / 2] * curIm
                    val bIm = re[i + k + len / 2] * curIm + im[i + k + len / 2] * curRe
                    re[i + k] = aRe + bRe; im[i + k] = aIm + bIm
                    re[i + k + len / 2] = aRe - bRe; im[i + k + len / 2] = aIm - bIm
                    val nRe = curRe * wRe - curIm * wIm
                    curIm = curRe * wIm + curIm * wRe; curRe = nRe
                }
                i += len
            }
            len = len shl 1
        }
    }

    companion object {
        const val HOP = 160
        const val NFFT = 512
        const val NMEL = 80
        const val MAX_FRAMES = 1501          // fixed 15 s window (AI Hub input_specs)
        const val PAD = 256
        const val PREEMPH = 0.97
        const val GUARD = 5.9604645e-8       // log_zero_guard + variance clamp
        const val STD_EPS = 1e-5

        /** Load the model's real window512 + mel filterbank from assets/stt/. */
        fun fromAssets(context: Context): MelFrontend {
            val win = readF32(context, "stt/mel_window512.f32")
            val fb = readF32(context, "stt/mel_fb.f32")
            require(win.size == NFFT) { "window512 must be $NFFT floats, got ${win.size}" }
            require(fb.size == (NFFT / 2 + 1) * NMEL) { "mel_fb must be ${(NFFT / 2 + 1) * NMEL} floats" }
            return MelFrontend(win, fb)
        }

        private fun readF32(context: Context, asset: String): FloatArray {
            val bytes = context.assets.open(asset).use { it.readBytes() }
            val bb = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
            return FloatArray(bytes.size / 4) { bb.float }
        }
    }
}
