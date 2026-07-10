package com.sankatmochan.mesh.model

import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Binary voice frames. Audio cannot ride [SosMessage]'s JSON envelope: base64 would cost
 * 33% of a channel that carries about 5 kbps. A voice frame is told apart from a JSON
 * envelope by its first byte — JSON always starts with '{' (0x7B), and 0xA5 is not a legal
 * UTF-8 lead byte, so the two can never be confused in either direction.
 *
 * Layout — must stay identical to `VOICE_STRUCT` in pi-code/envelope.py:
 *
 *   0      magic    0xA5
 *   1      version  2
 *   2      type     1 = voice chunk, 2 = NACK
 *   3..6   origin   4 ASCII chars
 *   7..8   seq      uint16, which clip
 *   9..10  index    uint16, which chunk        (NACK: 0)
 *   11..12 total    uint16, chunks in the clip
 *   13     hops     uint8
 *   14     codec    uint8                      (NACK: 0)
 *   15     attempt  uint8, 0 = first transmission
 *   16     length   uint8, payload bytes that follow
 *   17..            payload
 *
 * `attempt` is load-bearing. A resent chunk must carry a *different* id, or the mesh's
 * dedup — the thing that stops messages looping forever — silently drops the retry as a
 * duplicate and a clip that lost one frame can never be repaired.
 */
sealed interface VoiceFrame {
    /** Unique per frame; the mesh dedups on this. */
    val id: String
    /** Which recording this belongs to. */
    val clipId: String
    val hops: Int
    fun bumped(): VoiceFrame
    fun encode(): ByteArray
}

/** One slice of a recorded voice message. */
data class VoiceChunk(
    val origin: String,
    val seq: Int,
    val index: Int,
    val total: Int,
    val payload: ByteArray,
    override val hops: Int = 0,
    val codec: Int = CODEC_3GPP_AMR,
    val attempt: Int = 0,
) : VoiceFrame {

    override val id: String get() = "$origin-v$seq-$index#$attempt"
    override val clipId: String get() = "$origin-v$seq"

    override fun bumped(): VoiceChunk = copy(hops = minOf(hops + 1, MAX_HOPS))

    override fun encode(): ByteArray =
        pack(TYPE_CHUNK, origin, seq, index, total, hops, codec, attempt, payload)

    // ByteArray in a data class needs these; the generated ones compare references.
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (other !is VoiceChunk) return false
        return origin == other.origin && seq == other.seq && index == other.index &&
            total == other.total && hops == other.hops && codec == other.codec &&
            attempt == other.attempt && payload.contentEquals(other.payload)
    }

    override fun hashCode(): Int {
        var r = origin.hashCode()
        r = 31 * r + seq; r = 31 * r + index; r = 31 * r + total
        r = 31 * r + hops; r = 31 * r + codec; r = 31 * r + attempt
        return 31 * r + payload.contentHashCode()
    }

    companion object {
        const val MAGIC = 0xA5
        const val VERSION = 2
        const val TYPE_CHUNK = 1
        const val TYPE_NACK = 2
        const val HEADER = 17

        const val CODEC_OGG_OPUS = 1
        /** AMR-NB in a 3GPP container. Honours its 4.75 kbps setting, where the platform
         *  Opus encoder ignores the bitrate hint and lands near 14 kbps. */
        const val CODEC_3GPP_AMR = 2
        val KNOWN_CODECS = setOf(CODEC_OGG_OPUS, CODEC_3GPP_AMR)

        /** Keeps a frame at 217 B — inside LoRa's 255 and any sane BLE MTU. */
        const val MAX_CHUNK = 200
        /** A clip longer than this is not a rescue message. */
        const val MAX_CHUNKS = 512
        const val MAX_HOPS = 15
        /** First send plus six retries; then the clip is declared lost. */
        const val MAX_ATTEMPTS = 7

        fun extensionFor(codec: Int): String =
            if (codec == CODEC_3GPP_AMR) ".3gp" else ".ogg"

        /** True when these bytes are a voice frame rather than a JSON envelope. */
        fun looksLikeVoice(bytes: ByteArray): Boolean =
            bytes.isNotEmpty() && (bytes[0].toInt() and 0xFF) == MAGIC

        internal fun pack(
            type: Int, origin: String, seq: Int, index: Int, total: Int,
            hops: Int, codec: Int, attempt: Int, payload: ByteArray,
        ): ByteArray {
            require(payload.size <= MAX_CHUNK) { "voice payload ${payload.size} > $MAX_CHUNK" }
            val originBytes = ByteArray(4)
            val ascii = origin.toByteArray(Charsets.US_ASCII)
            ascii.copyInto(originBytes, 0, 0, minOf(4, ascii.size))
            return ByteBuffer.allocate(HEADER + payload.size).order(ByteOrder.BIG_ENDIAN).apply {
                put(MAGIC.toByte()); put(VERSION.toByte()); put(type.toByte())
                put(originBytes)
                putShort(seq.toShort()); putShort(index.toShort()); putShort(total.toShort())
                put(minOf(hops, MAX_HOPS).toByte()); put(codec.toByte())
                put(attempt.toByte()); put(payload.size.toByte())
                put(payload)
            }.array()
        }

        private fun originOf(bytes: ByteArray): String? {
            // Python's encode() right-pads with NUL, not spaces.
            val s = String(bytes, Charsets.US_ASCII).trimEnd('\u0000')
            return if (s.isNotEmpty() && s.all { it.isLetterOrDigit() }) s else null
        }

        /**
         * Parse + validate. Untrusted input (CLAUDE.md #8): every field is range-checked
         * and the declared length must match the frame exactly. Returns null to drop.
         */
        fun decode(bytes: ByteArray): VoiceFrame? {
            if (bytes.size < HEADER || bytes.size > HEADER + MAX_CHUNK) return null
            val bb = ByteBuffer.wrap(bytes).order(ByteOrder.BIG_ENDIAN)

            if ((bb.get().toInt() and 0xFF) != MAGIC) return null
            if ((bb.get().toInt() and 0xFF) != VERSION) return null
            val type = bb.get().toInt() and 0xFF
            if (type != TYPE_CHUNK && type != TYPE_NACK) return null

            val originBytes = ByteArray(4).also { bb.get(it) }
            val seq = bb.short.toInt() and 0xFFFF
            val index = bb.short.toInt() and 0xFFFF
            val total = bb.short.toInt() and 0xFFFF
            val hops = bb.get().toInt() and 0xFF
            val codec = bb.get().toInt() and 0xFF
            val attempt = bb.get().toInt() and 0xFF
            val length = bb.get().toInt() and 0xFF

            if (total < 1 || total > MAX_CHUNKS) return null
            if (length > MAX_CHUNK || bytes.size != HEADER + length) return null
            if (attempt >= MAX_ATTEMPTS) return null
            val origin = originOf(originBytes) ?: return null
            val body = ByteArray(length).also { bb.get(it) }

            if (type == TYPE_CHUNK) {
                if (codec !in KNOWN_CODECS || index >= total) return null
                return VoiceChunk(origin, seq, index, total, body, minOf(hops, MAX_HOPS), codec, attempt)
            }

            // NACK: 4-byte clip origin, then a bitmap covering exactly `total` chunks.
            val need = 4 + (total + 7) / 8
            if (body.size != need) return null
            val clipOrigin = originOf(body.copyOfRange(0, 4)) ?: return null
            val missing = (0 until total).filter {
                (body[4 + it / 8].toInt() shr (it % 8)) and 1 == 1
            }
            if (missing.isEmpty()) return null   // a NACK asking for nothing is malformed
            return VoiceNack(origin, clipOrigin, seq, total, missing, minOf(hops, MAX_HOPS), attempt)
        }

        /** Split an encoded clip into wire-ready chunks. */
        fun split(origin: String, seq: Int, clip: ByteArray, codec: Int): List<VoiceChunk> {
            val total = (clip.size + MAX_CHUNK - 1) / MAX_CHUNK
            require(total in 1..MAX_CHUNKS) { "clip needs $total chunks" }
            return (0 until total).map { i ->
                val from = i * MAX_CHUNK
                val to = minOf(from + MAX_CHUNK, clip.size)
                VoiceChunk(origin, seq, i, total, clip.copyOfRange(from, to), codec = codec)
            }
        }
    }
}

/**
 * "Clip <clipOrigin>-v<seq>: I am missing these pieces."
 *
 * [origin] is the REQUESTER, not the clip's author, so two responders asking for the same
 * clip produce two distinct ids and neither is dedup'd away.
 */
data class VoiceNack(
    val origin: String,
    val clipOrigin: String,
    val seq: Int,
    val total: Int,
    val missing: List<Int>,
    override val hops: Int = 0,
    val attempt: Int = 0,
) : VoiceFrame {

    override val id: String get() = "$origin-n${clipOrigin}v$seq#$attempt"
    override val clipId: String get() = "$clipOrigin-v$seq"

    override fun bumped(): VoiceNack = copy(hops = minOf(hops + 1, VoiceChunk.MAX_HOPS))

    override fun encode(): ByteArray {
        val bitmap = ByteArray((total + 7) / 8)
        for (i in missing) bitmap[i / 8] = (bitmap[i / 8].toInt() or (1 shl (i % 8))).toByte()
        val originBytes = ByteArray(4)
        clipOrigin.toByteArray(Charsets.US_ASCII).copyInto(originBytes, 0, 0, minOf(4, clipOrigin.length))
        return VoiceChunk.pack(
            VoiceChunk.TYPE_NACK, origin, seq, 0, total, hops, 0, attempt, originBytes + bitmap
        )
    }
}
