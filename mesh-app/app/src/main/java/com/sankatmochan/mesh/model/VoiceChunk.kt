package com.sankatmochan.mesh.model

import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * One slice of a recorded voice message.
 *
 * Audio cannot ride [SosMessage]'s JSON envelope: base64 would cost 33% of a channel
 * that carries about 5 kbps. So a voice chunk is a binary frame, told apart from a JSON
 * envelope by its first byte — JSON always starts with '{' (0x7B), and 0xA5 is not a
 * legal UTF-8 lead byte, so the two can never be confused in either direction.
 *
 * Byte layout — must stay identical to `VOICE_STRUCT` in pi-code/envelope.py:
 *
 *   0      magic    0xA5
 *   1      version  1
 *   2      type     1 = voice
 *   3..6   origin   4 ASCII chars (the phone's node id)
 *   7..8   seq      uint16, which clip from this phone
 *   9..10  index    uint16, which chunk of that clip
 *   11..12 total    uint16, how many chunks the clip has
 *   13     hops     uint8
 *   14     codec    uint8
 *   15     length   uint8, payload bytes that follow
 *   16..            payload
 *
 * The chunk is shaped like an envelope on purpose: it has an [id] and [hops], so the
 * mesh's dedup and store-and-forward carry it without knowing what it is. Only the
 * phones ever reassemble a clip.
 */
data class VoiceChunk(
    val origin: String,
    val seq: Int,
    val index: Int,
    val total: Int,
    val payload: ByteArray,
    val hops: Int = 0,
    val codec: Int = CODEC_3GPP_AMR,
) {
    /** Unique per chunk, so mesh dedup drops a repeat without dropping the clip. */
    val id: String get() = "$origin-v$seq-$index"

    /** Every chunk of one recording shares this. */
    val clipId: String get() = "$origin-v$seq"

    fun bumped(): VoiceChunk = copy(hops = minOf(hops + 1, MAX_HOPS))

    fun encode(): ByteArray {
        require(payload.size <= MAX_CHUNK) { "voice payload ${payload.size} > $MAX_CHUNK" }
        val originBytes = ByteArray(4)
        val ascii = origin.toByteArray(Charsets.US_ASCII)
        ascii.copyInto(originBytes, 0, 0, minOf(4, ascii.size))

        return ByteBuffer.allocate(HEADER + payload.size).order(ByteOrder.BIG_ENDIAN).apply {
            put(MAGIC.toByte())
            put(VERSION.toByte())
            put(TYPE_VOICE.toByte())
            put(originBytes)
            putShort(seq.toShort())
            putShort(index.toShort())
            putShort(total.toShort())
            put(minOf(hops, MAX_HOPS).toByte())
            put(codec.toByte())
            put(payload.size.toByte())
            put(payload)
        }.array()
    }

    // ByteArray in a data class needs these; the generated ones compare references.
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (other !is VoiceChunk) return false
        return origin == other.origin && seq == other.seq && index == other.index &&
            total == other.total && hops == other.hops && codec == other.codec &&
            payload.contentEquals(other.payload)
    }

    override fun hashCode(): Int {
        var r = origin.hashCode()
        r = 31 * r + seq; r = 31 * r + index; r = 31 * r + total
        r = 31 * r + hops; r = 31 * r + codec
        return 31 * r + payload.contentHashCode()
    }

    companion object {
        const val MAGIC = 0xA5
        const val VERSION = 1
        const val TYPE_VOICE = 1
        const val HEADER = 16
        const val CODEC_OGG_OPUS = 1
        /** AMR-NB in a 3GPP container. Honours its 4.75 kbps setting, where the platform
         *  Opus encoder ignores the bitrate hint and lands near 14 kbps. */
        const val CODEC_3GPP_AMR = 2
        val KNOWN_CODECS = setOf(CODEC_OGG_OPUS, CODEC_3GPP_AMR)

        /** File suffix a MediaPlayer will recognise for each codec. */
        fun extensionFor(codec: Int): String =
            if (codec == CODEC_3GPP_AMR) ".3gp" else ".ogg"

        /** Keeps a frame at 216 B — inside LoRa's 255 and any sane BLE MTU. */
        const val MAX_CHUNK = 200
        /** A clip longer than this is not a rescue message. */
        const val MAX_CHUNKS = 512
        const val MAX_HOPS = 15

        /** True when these bytes are a voice frame rather than a JSON envelope. */
        fun looksLikeVoice(bytes: ByteArray): Boolean =
            bytes.isNotEmpty() && (bytes[0].toInt() and 0xFF) == MAGIC

        /**
         * Parse + validate. Untrusted input (CLAUDE.md #8): every field is range-checked
         * and the declared length must match the frame exactly. Returns null to drop.
         */
        fun decode(bytes: ByteArray): VoiceChunk? {
            if (bytes.size < HEADER || bytes.size > HEADER + MAX_CHUNK) return null
            val bb = ByteBuffer.wrap(bytes).order(ByteOrder.BIG_ENDIAN)

            if ((bb.get().toInt() and 0xFF) != MAGIC) return null
            if ((bb.get().toInt() and 0xFF) != VERSION) return null
            if ((bb.get().toInt() and 0xFF) != TYPE_VOICE) return null

            val originBytes = ByteArray(4).also { bb.get(it) }
            val seq = bb.short.toInt() and 0xFFFF
            val index = bb.short.toInt() and 0xFFFF
            val total = bb.short.toInt() and 0xFFFF
            val hops = bb.get().toInt() and 0xFF
            val codec = bb.get().toInt() and 0xFF
            val length = bb.get().toInt() and 0xFF

            if (codec !in KNOWN_CODECS) return null
            if (total < 1 || total > MAX_CHUNKS || index >= total) return null
            if (length > MAX_CHUNK || bytes.size != HEADER + length) return null

            val origin = String(originBytes, Charsets.US_ASCII).trimEnd('\u0000')  // Python encode() right-pads with NUL
            if (origin.isEmpty() || !origin.all { it.isLetterOrDigit() }) return null

            val payload = ByteArray(length).also { bb.get(it) }
            return VoiceChunk(
                origin = origin, seq = seq, index = index, total = total,
                payload = payload, hops = minOf(hops, MAX_HOPS), codec = codec
            )
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
