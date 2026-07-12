package com.sankatmochan.mesh.model

import com.google.common.truth.Truth.assertThat
import org.junit.Test

/**
 * Binary voice-frame framing. Every [VoiceChunk.decode] path is an untrusted-input guard
 * (CLAUDE.md #8), so the negative cases matter as much as the round-trips.
 */
class VoiceChunkTest {

    // ── Chunks ──────────────────────────────────────────────────────────────────

    @Test fun `chunk survives an encode-decode round trip`() {
        val payload = ByteArray(50) { it.toByte() }
        val chunk = VoiceChunk("ab12", seq = 7, index = 2, total = 4, payload = payload,
            codec = VoiceChunk.CODEC_3GPP_AMR)
        val decoded = VoiceChunk.decode(chunk.encode())
        assertThat(decoded).isInstanceOf(VoiceChunk::class.java)
        decoded as VoiceChunk
        assertThat(decoded.origin).isEqualTo("ab12")
        assertThat(decoded.seq).isEqualTo(7)
        assertThat(decoded.index).isEqualTo(2)
        assertThat(decoded.total).isEqualTo(4)
        assertThat(decoded.codec).isEqualTo(VoiceChunk.CODEC_3GPP_AMR)
        assertThat(decoded.payload).isEqualTo(payload)
    }

    @Test fun `looksLikeVoice keys on the magic byte`() {
        val voice = VoiceChunk("ab12", 0, 0, 1, byteArrayOf(1, 2, 3)).encode()
        assertThat(VoiceChunk.looksLikeVoice(voice)).isTrue()
        assertThat(VoiceChunk.looksLikeVoice("{".toByteArray())).isFalse() // a JSON envelope
        assertThat(VoiceChunk.looksLikeVoice(ByteArray(0))).isFalse()
    }

    @Test fun `decode rejects a wrong magic byte`() {
        val bytes = VoiceChunk("ab12", 0, 0, 1, byteArrayOf(9)).encode()
        bytes[0] = 0x00
        assertThat(VoiceChunk.decode(bytes)).isNull()
    }

    @Test fun `decode rejects a wrong version`() {
        val bytes = VoiceChunk("ab12", 0, 0, 1, byteArrayOf(9)).encode()
        bytes[1] = 99
        assertThat(VoiceChunk.decode(bytes)).isNull()
    }

    @Test fun `decode rejects a length that disagrees with the frame size`() {
        val bytes = VoiceChunk("ab12", 0, 0, 1, byteArrayOf(1, 2, 3, 4)).encode()
        bytes[16] = 99 // declared length field no longer matches actual payload
        assertThat(VoiceChunk.decode(bytes)).isNull()
    }

    @Test fun `decode rejects an unknown codec`() {
        val bytes = VoiceChunk("ab12", 0, 0, 1, byteArrayOf(1)).encode()
        bytes[14] = 42 // codec byte
        assertThat(VoiceChunk.decode(bytes)).isNull()
    }

    @Test fun `decode rejects index outside total`() {
        // index(9..10) = 5 with total(11..12) = 4 -> index >= total, invalid.
        val bytes = VoiceChunk("ab12", 0, index = 0, total = 4, payload = byteArrayOf(1)).encode()
        bytes[10] = 5 // low byte of index
        assertThat(VoiceChunk.decode(bytes)).isNull()
    }

    @Test fun `decode rejects an over-large attempt`() {
        val bytes = VoiceChunk("ab12", 0, 0, 1, byteArrayOf(1), attempt = 0).encode()
        bytes[15] = VoiceChunk.MAX_ATTEMPTS.toByte() // == MAX_ATTEMPTS is out of range
        assertThat(VoiceChunk.decode(bytes)).isNull()
    }

    @Test fun `decode rejects a non-alphanumeric origin`() {
        val bytes = VoiceChunk("ab12", 0, 0, 1, byteArrayOf(1)).encode()
        bytes[3] = '/'.code.toByte()
        assertThat(VoiceChunk.decode(bytes)).isNull()
    }

    @Test fun `decode rejects a truncated frame`() {
        assertThat(VoiceChunk.decode(ByteArray(VoiceChunk.HEADER - 1))).isNull()
    }

    @Test fun `pack refuses a payload larger than MAX_CHUNK`() {
        val tooBig = ByteArray(VoiceChunk.MAX_CHUNK + 1)
        try {
            VoiceChunk("ab12", 0, 0, 1, tooBig).encode()
            throw AssertionError("expected IllegalArgumentException")
        } catch (_: IllegalArgumentException) { /* expected */ }
    }

    @Test fun `bumped increments hops up to the ceiling`() {
        var chunk = VoiceChunk("ab12", 0, 0, 1, byteArrayOf(1), hops = 0)
        repeat(20) { chunk = chunk.bumped() }
        assertThat(chunk.hops).isEqualTo(VoiceChunk.MAX_HOPS)
    }

    @Test fun `resent chunk gets a distinct id so dedup does not eat the retry`() {
        val first = VoiceChunk("ab12", 3, 1, 5, byteArrayOf(1), attempt = 0)
        val retry = first.copy(attempt = 1)
        assertThat(retry.id).isNotEqualTo(first.id)
        assertThat(retry.clipId).isEqualTo(first.clipId) // same clip, different frame id
    }

    // ── split ─────────────────────────────────────────────────────────────────

    @Test fun `split covers the whole clip in ceil-sized chunks`() {
        val clip = ByteArray(VoiceChunk.MAX_CHUNK * 2 + 10)
        val chunks = VoiceChunk.split("ab12", 0, clip, VoiceChunk.CODEC_3GPP_AMR)
        assertThat(chunks).hasSize(3)
        assertThat(chunks.sumOf { it.payload.size }).isEqualTo(clip.size)
        chunks.forEachIndexed { i, c ->
            assertThat(c.index).isEqualTo(i)
            assertThat(c.total).isEqualTo(3)
        }
    }

    // ── NACK ────────────────────────────────────────────────────────────────────

    @Test fun `nack survives an encode-decode round trip`() {
        val nack = VoiceNack(origin = "req9", clipOrigin = "ab12", seq = 4, total = 10,
            missing = listOf(0, 3, 9))
        val decoded = VoiceChunk.decode(nack.encode())
        assertThat(decoded).isInstanceOf(VoiceNack::class.java)
        decoded as VoiceNack
        assertThat(decoded.origin).isEqualTo("req9")
        assertThat(decoded.clipOrigin).isEqualTo("ab12")
        assertThat(decoded.seq).isEqualTo(4)
        assertThat(decoded.total).isEqualTo(10)
        assertThat(decoded.missing).containsExactly(0, 3, 9).inOrder()
    }

    @Test fun `a nack asking for nothing is rejected as malformed`() {
        // Hand-build a NACK whose bitmap is all zeros; decode must drop it.
        val total = 8
        val body = ByteArray(4 + (total + 7) / 8)
        "ab12".toByteArray(Charsets.US_ASCII).copyInto(body)
        val bytes = VoiceChunk.pack(VoiceChunk.TYPE_NACK, "req9", 0, 0, total, 0, 0, 0, body)
        assertThat(VoiceChunk.decode(bytes)).isNull()
    }
}
