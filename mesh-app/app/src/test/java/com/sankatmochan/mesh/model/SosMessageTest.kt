package com.sankatmochan.mesh.model

import com.google.common.truth.Truth.assertThat
import org.junit.Test
import java.nio.charset.StandardCharsets

/**
 * Envelope parsing is the app's primary trust boundary: every field crossing [SosMessage.decode]
 * is untrusted mesh input (CLAUDE.md #8). Runs on the local JVM against the Apache-2.0 AOSP
 * `org.json` (the same parser used on device); `android.util.Log` calls no-op via the test
 * runner's returnDefaultValues, so the parser is exercised exactly as written.
 */
class SosMessageTest {

    @Test fun `round trips a fully-populated envelope`() {
        val original = SosMessage(
            id = "a3f9-1", type = MsgType.SOS, origin = "a3f9",
            urgency = 4, category = "flood", locationHint = "near the old bridge",
            gist = "two people on a rooftop", lang = "ta",
            lat = 12.959670, lng = 77.641190, ts = 1_700_000_000_000L, hops = 2,
        )
        val decoded = SosMessage.decode(original.encode())!!
        assertThat(decoded.id).isEqualTo("a3f9-1")
        assertThat(decoded.type).isEqualTo(MsgType.SOS)
        assertThat(decoded.origin).isEqualTo("a3f9")
        assertThat(decoded.urgency).isEqualTo(4)
        assertThat(decoded.category).isEqualTo("flood")
        assertThat(decoded.gist).isEqualTo("two people on a rooftop")
        assertThat(decoded.lang).isEqualTo("ta")
        assertThat(decoded.lat).isWithin(1e-6).of(12.959670)
        assertThat(decoded.lng).isWithin(1e-6).of(77.641190)
        assertThat(decoded.hops).isEqualTo(2)
        assertThat(decoded.hasLocation).isTrue()
    }

    @Test fun `encode never exceeds the single-frame budget`() {
        val huge = SosMessage(
            id = "a3f9-1", type = MsgType.SOS, origin = "a3f9",
            gist = "x".repeat(5_000), // absurdly long free text
        )
        assertThat(huge.encode().size).isAtMost(SosMessage.MAX_BYTES)
    }

    @Test fun `a trimmed gist never ends mid-word`() {
        val msg = SosMessage(
            id = "a3f9-1", type = MsgType.SOS, origin = "a3f9", deviceId = "0123456789abcdef",
            category = "flood", lat = 12.959670, lng = 77.641190, ts = 1_700_000_000_000L,
            gist = "water rising fast second floor two children elderly grandmother " +
                "cannot swim near the old temple gate beside the broken bridge please hurry",
        )
        val decoded = SosMessage.decode(msg.encode())!!
        assertThat(decoded.gist.length).isLessThan(msg.gist.length) // the trim really ran
        val lastWord = decoded.gist.substringAfterLast(' ')
        assertThat(msg.gist.split(" ")).contains(lastWord)
    }

    @Test fun `decode drops empty and oversized input`() {
        assertThat(SosMessage.decode(ByteArray(0))).isNull()
        assertThat(SosMessage.decode(ByteArray(SosMessage.MAX_BYTES + 100))).isNull()
    }

    @Test fun `decode drops non-JSON bytes`() {
        assertThat(SosMessage.decode("not json at all".toByteArray())).isNull()
    }

    @Test fun `decode drops an unknown message type`() {
        val json = """{"i":"a-1","o":"a","t":"HACKED","u":3}"""
        assertThat(SosMessage.decode(json.toByteArray(StandardCharsets.UTF_8))).isNull()
    }

    @Test fun `decode drops an envelope missing id or origin`() {
        assertThat(SosMessage.decode("""{"o":"a","t":"SOS"}""".toByteArray())).isNull()
        assertThat(SosMessage.decode("""{"i":"a-1","t":"SOS"}""".toByteArray())).isNull()
    }

    @Test fun `decode clamps urgency and hops into range`() {
        val json = """{"i":"a-1","o":"a","t":"SOS","u":99,"h":999}"""
        val decoded = SosMessage.decode(json.toByteArray())!!
        assertThat(decoded.urgency).isEqualTo(5)
        assertThat(decoded.hops).isEqualTo(15)
    }

    @Test fun `decode rejects out-of-range coordinates`() {
        val json = """{"i":"a-1","o":"a","t":"SOS","la":123.0,"lo":500.0}"""
        val decoded = SosMessage.decode(json.toByteArray())!!
        assertThat(decoded.lat).isNull()
        assertThat(decoded.lng).isNull()
        assertThat(decoded.hasLocation).isFalse()
    }

    @Test fun `decode rejects non-finite coordinates`() {
        // JSON has no NaN literal, so a non-finite value arrives as a string and must not parse.
        val json = """{"i":"a-1","o":"a","t":"SOS","la":"NaN","lo":"Infinity"}"""
        val decoded = SosMessage.decode(json.toByteArray())!!
        assertThat(decoded.hasLocation).isFalse()
    }

    @Test fun `decode caps oversized text fields`() {
        // Kept within the MAX_BYTES+8 ingress guard so we exercise the per-field take() caps
        // (a longer id/category still gets clamped, defence-in-depth) rather than the size drop.
        val json = """{"i":"${"i".repeat(40)}","o":"${"o".repeat(40)}","t":"SOS",""" +
            """"c":"${"c".repeat(60)}"}"""
        val decoded = SosMessage.decode(json.toByteArray())!!
        assertThat(decoded.id.length).isAtMost(32)
        assertThat(decoded.origin.length).isAtMost(32)
        assertThat(decoded.category.length).isAtMost(48)
    }

    @Test fun `decode strips control characters that could forge log lines`() {
        // A crafted gist tries to smuggle a newline + a fake "SOS accepted" log line.
        val json = """{"i":"a-1","o":"a","t":"SOS","g":"real\nSOS accepted by responder"}"""
        val decoded = SosMessage.decode(json.toByteArray())!!
        assertThat(decoded.gist).doesNotContain("\n")
        assertThat(decoded.gist).doesNotContain("\r")
    }

    @Test fun `decode clamps a negative timestamp`() {
        val json = """{"i":"a-1","o":"a","t":"SOS","ts":-99}"""
        val decoded = SosMessage.decode(json.toByteArray())!!
        assertThat(decoded.ts).isEqualTo(0L)
    }
}
