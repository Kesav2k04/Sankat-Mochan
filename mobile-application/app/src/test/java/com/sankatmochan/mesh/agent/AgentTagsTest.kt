package com.sankatmochan.mesh.agent

import com.google.common.truth.Truth.assertThat
import org.junit.Test

/**
 * The TAGS wire is what the command post and responder phones act on — a pair cut in half
 * by the envelope's byte trim is silently dropped downstream, which means rescuers lose
 * facts without anyone knowing. These tests pin the guarantee that [AgentTags.build] fits
 * a byte budget by dropping WHOLE pairs / WHOLE landmark words, never by cutting mid-pair.
 */
class AgentTagsTest {

    private val fullTags = mapOf(
        "unresp" to "y", "c" to "3", "inj" to "fracture", "trap" to "y",
        "hz" to "collapse", "mob" to "n", "lm" to "old temple gate near the broken bridge",
    )

    @Test fun `build without a budget carries every valid tag`() {
        val wire = AgentTags.build(fullTags)!!
        val parsed = AgentTags.parse(wire)!!
        assertThat(parsed).containsExactlyEntriesIn(
            fullTags.mapValues { (k, v) -> if (k == "lm") v else v.lowercase() }
        )
    }

    @Test fun `build fits the byte budget and still parses cleanly`() {
        for (budget in 20..130) {
            val wire = AgentTags.build(fullTags, budget) ?: continue
            assertThat(wire.toByteArray(Charsets.UTF_8).size).isAtMost(budget)
            // Every pair on the wire must be complete — parse recovers it verbatim.
            val parsed = AgentTags.parse(wire)!!
            for ((k, v) in parsed) {
                if (k != "lm") assertThat(fullTags[k]).isEqualTo(v)
            }
        }
    }

    @Test fun `critical tags survive a tight budget before the landmark`() {
        // 78 bytes = the real budget left by a fully-populated envelope.
        val wire = AgentTags.build(fullTags, 78)!!
        val parsed = AgentTags.parse(wire)!!
        assertThat(parsed).containsEntry("unresp", "y")
        assertThat(parsed).containsEntry("c", "3")
        assertThat(parsed).containsEntry("inj", "fracture")
        assertThat(parsed).containsEntry("trap", "y")
    }

    @Test fun `landmark is shed whole words at a time, never cut mid-word`() {
        val wire = AgentTags.build(fullTags, 90)!!
        val parsed = AgentTags.parse(wire)!!
        parsed["lm"]?.let { lm ->
            // Whatever survived must be a prefix of the landmark ending on a word boundary.
            val source = "old temple gate near the broken bridge"
            assertThat(source).startsWith(lm)
            assertThat(lm.length == source.length || source[lm.length] == ' ').isTrue()
        }
    }

    @Test fun `a multibyte landmark fits by bytes not chars`() {
        val tags = mapOf("c" to "2", "lm" to "பழைய கோவில் வாசல் அருகே")
        val wire = AgentTags.build(tags, 40)!!
        assertThat(wire.toByteArray(Charsets.UTF_8).size).isAtMost(40)
        assertThat(AgentTags.parse(wire)!!).containsEntry("c", "2")
    }

    @Test fun `capLandmark cuts on a word boundary`() {
        val long = "a".repeat(20) + " " + "b".repeat(20) + " " + "c".repeat(20)
        val capped = AgentTags.capLandmark(long)
        assertThat(capped.length).isAtMost(AgentTags.LM_MAX)
        assertThat(capped).isEqualTo("a".repeat(20) + " " + "b".repeat(20))
    }

    @Test fun `build returns null when nothing fits`() {
        assertThat(AgentTags.build(fullTags, 5)).isNull()
        assertThat(AgentTags.build(emptyMap())).isNull()
    }

    @Test fun `parse keeps the head of a wire whose tail was cut by a relay`() {
        // An old-build phone or relay can still hand us a blunt-cut wire.
        val parsed = AgentTags.parse("TAGS unresp:y c:3 inj:ble")!!
        assertThat(parsed).containsEntry("unresp", "y")
        assertThat(parsed).containsEntry("c", "3")
        assertThat(parsed).doesNotContainKey("inj")
    }

    @Test fun `humanize never echoes raw wire syntax`() {
        val text = AgentTags.humanize(AgentTags.parse(AgentTags.build(fullTags)!!)!!)
        assertThat(text).doesNotContain(":")
        assertThat(text).contains("3 people")
        assertThat(text).contains("UNRESPONSIVE")
    }
}
