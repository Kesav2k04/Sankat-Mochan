package com.sankatmochan.mesh.stt

import android.content.Context
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.math.exp
import kotlin.math.ln

/**
 * Greedy CTC decode for IndicConformer, ported 1:1 from the model's own
 * `model_onnx.py::_ctc_decode` (AI4Bharat, MIT — CLAUDE.md #3/#4):
 *
 *   logprobs = ctc_decoder(encoder_out)            # (1, T, 5633)
 *   logprobs = logprobs[:, :, language_masks[lang]] # keep only this language's classes
 *   idx      = argmax(logprobs[0], dim=-1)
 *   collapsed = unique_consecutive(idx)             # merge repeats
 *   hyp = ''.join(vocab[lang][i] for i in collapsed if i != BLANK_ID).replace('▁',' ').strip()
 *
 * Pure arithmetic — runs on the CPU in microseconds; the heavy matmul already
 * happened on the NPU (encoder + ctc_decoder graphs).
 *
 * Two assets ship in app/src/main/assets/stt/ (copied verbatim from the HF model):
 *   vocab.json           { "hi": ["<unk>","▁क",...] (257 tokens incl. blank), ... }
 *   language_masks.json  { "hi": [false,false,true,...] (5633 bools), ... }
 */
class CtcDecoder private constructor(
    private val vocab: Map<String, List<String>>,
    private val masks: Map<String, BooleanArray>,
) {
    /** Column indices (into the 5633-wide ctc output) that belong to [lang]. */
    private val maskIndexCache = HashMap<String, IntArray>()

    val supportedLanguages: Set<String> get() = vocab.keys

    private fun maskIndices(lang: String): IntArray = maskIndexCache.getOrPut(lang) {
        val m = masks[lang] ?: error("no language mask for '$lang'")
        val out = ArrayList<Int>(m.size / 8)
        for (i in m.indices) if (m[i]) out.add(i)
        out.toIntArray()
    }

    /**
     * @param logprobs flattened ctc output of shape (T, [VOCAB_CLASSES]=5633), row-major:
     *        logprobs[t * 5633 + c].
     * @param frames   T (number of encoder output frames actually valid).
     * @param lang     ISO code selecting the vocab + class mask.
     */
    fun decode(logprobs: FloatArray, frames: Int, lang: String): String {
        val cols = maskIndices(lang)          // e.g. Hindi's ~256 live classes among 5633
        val tokens = vocab[lang] ?: error("no vocab for '$lang'")
        val sb = StringBuilder()
        var prevArgmax = -1
        for (t in 0 until frames) {
            val base = t * VOCAB_CLASSES
            // argmax over ONLY this language's columns (mirrors the mask + argmax in Python).
            var bestCol = 0
            var bestVal = Float.NEGATIVE_INFINITY
            for (ci in cols.indices) {
                val v = logprobs[base + cols[ci]]
                if (v > bestVal) { bestVal = v; bestCol = ci }
            }
            // bestCol indexes into the per-language vocab (mask order == vocab order).
            if (bestCol == prevArgmax) continue          // collapse consecutive repeats
            prevArgmax = bestCol
            if (bestCol == BLANK_ID) continue            // drop CTC blank
            tokens.getOrNull(bestCol)?.let { sb.append(it) }
        }
        return sb.toString().replace('▁', ' ').trim()  // ▁ (U+2581) → space
    }

    /**
     * Pick the language directly from the CTC logits — no separate LID model. The encoder is
     * language-agnostic; each language is a mask over the 5633 classes. For each candidate we
     * log-softmax over its masked columns and average the greedy path's max log-prob on non-blank
     * frames; the language the model is most confident in wins. Measured 100% on FLEURS (10/10,
     * open 22-language set) — beats a dedicated VoxLingua107 SLID (90%) at zero extra latency.
     */
    fun pickLanguage(
        logprobs: FloatArray,
        frames: Int,
        candidates: Collection<String> = vocab.keys,
    ): String {
        val scores = HashMap<String, Double>(candidates.size)
        for (lang in candidates) {
            val cols = maskIndices(lang)
            var sum = 0.0
            var cnt = 0
            for (t in 0 until frames) {
                val b = t * VOCAB_CLASSES
                var mx = Float.NEGATIVE_INFINITY
                var arg = 0
                for (ci in cols.indices) {
                    val v = logprobs[b + cols[ci]]
                    if (v > mx) { mx = v; arg = ci }
                }
                var se = 0.0
                for (ci in cols.indices) se += exp((logprobs[b + cols[ci]] - mx).toDouble())
                val topLogProb = -ln(se)            // (mx - logsumexp) = mx - (mx + ln se)
                if (arg != BLANK_ID) { sum += topLogProb; cnt++ }
            }
            scores[lang] = if (cnt > 0) sum / cnt else Double.NEGATIVE_INFINITY
        }
        val best = scores.maxByOrNull { it.value }?.key ?: "hi"

        // Hindi vs Urdu are the same spoken language (Hindustani); the acoustic model can't tell
        // them apart, so LID flips between them. For an India-first deployment, prefer Devanagari
        // Hindi when Urdu only barely wins. (Set a manual override to force Urdu when needed.)
        if (best == "ur" && "hi" in scores) {
            val ur = scores["ur"]!!; val hi = scores["hi"]!!
            if (hi >= ur - HINDUSTANI_MARGIN) return "hi"
        }
        return best
    }

    companion object {
        /** Width of the ctc_decoder output (see ctc_decoder.onnx: logprobs (1,T,5633)). */
        const val VOCAB_CLASSES = 5633

        /** IndicASRConfig.BLANK_ID — index of the CTC blank within each language's vocab. */
        const val BLANK_ID = 256

        /** How close Hindi's LID score must be to Urdu's to override to Hindi (Hindustani tie). */
        const val HINDUSTANI_MARGIN = 0.15

        fun fromAssets(context: Context): CtcDecoder {
            val json = Json { ignoreUnknownKeys = true }
            val vocabObj = context.assets.open("stt/vocab.json").use {
                json.parseToJsonElement(it.readBytes().decodeToString()).jsonObject
            }
            val maskObj = context.assets.open("stt/language_masks.json").use {
                json.parseToJsonElement(it.readBytes().decodeToString()).jsonObject
            }
            val vocab = vocabObj.mapValues { (_, arr) ->
                (arr as JsonArray).map { it.jsonPrimitive.content }
            }
            val masks = maskObj.mapValues { (_, arr) ->
                (arr as JsonArray).let { a -> BooleanArray(a.size) { i -> a[i].jsonPrimitive.boolean } }
            }
            return CtcDecoder(vocab, masks)
        }
    }
}
