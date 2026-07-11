package com.sankatmochan.mesh.mesh

import com.google.common.truth.Truth.assertThat
import com.sankatmochan.mesh.model.MsgType
import com.sankatmochan.mesh.model.SosMessage
import org.junit.Test

/** State-store behaviour: dedup, urgency/recency ordering, and the DoS-bounding caps. */
class MessageStoreTest {

    private fun sos(id: String, urgency: Int = 3, ts: Long = 0L) =
        SosMessage(id = id, type = MsgType.SOS, origin = id.substringBefore('-'),
            urgency = urgency, ts = ts)

    @Test fun `markSeen dedups an id`() {
        val store = MessageStore()
        assertThat(store.markSeen("a-1")).isTrue()
        assertThat(store.markSeen("a-1")).isFalse()
    }

    @Test fun `received SOS is ordered by urgency then recency`() {
        val store = MessageStore()
        store.addReceivedSos(sos("a-1", urgency = 2, ts = 100))
        store.addReceivedSos(sos("a-2", urgency = 5, ts = 50))
        store.addReceivedSos(sos("a-3", urgency = 5, ts = 60))
        val ids = store.receivedSos.value.map { it.id }
        assertThat(ids).containsExactly("a-3", "a-2", "a-1").inOrder()
    }

    @Test fun `received SOS is deduped by id`() {
        val store = MessageStore()
        store.addReceivedSos(sos("a-1", urgency = 3, ts = 10))
        store.addReceivedSos(sos("a-1", urgency = 3, ts = 10))
        assertThat(store.receivedSos.value).hasSize(1)
    }

    @Test fun `received SOS list is capped against a flood`() {
        val store = MessageStore()
        repeat(500) { store.addReceivedSos(sos("a-$it", urgency = 3, ts = it.toLong())) }
        assertThat(store.receivedSos.value.size).isAtMost(300)
    }

    @Test fun `the cap keeps the most urgent messages`() {
        val store = MessageStore()
        // 400 low-urgency messages, then one critical - the critical must survive the cap.
        repeat(400) { store.addReceivedSos(sos("low-$it", urgency = 1, ts = it.toLong())) }
        store.addReceivedSos(sos("crit-1", urgency = 5, ts = 999))
        assertThat(store.receivedSos.value.first().id).isEqualTo("crit-1")
        assertThat(store.receivedSos.value.any { it.id == "crit-1" }).isTrue()
    }

    @Test fun `sent status only advances, never regresses`() {
        val store = MessageStore()
        store.addSent(sos("me-1"))
        store.updateSentStatus("me-1", stage = 2, text = "Help is on the way")
        store.updateSentStatus("me-1", stage = 1, text = "reached control room") // stale, lower
        val sent = store.sent.value.single()
        assertThat(sent.stage).isEqualTo(2)
        assertThat(sent.statusText).isEqualTo("Help is on the way")
    }

    @Test fun `event log is bounded`() {
        val store = MessageStore()
        repeat(250) { store.log("line-$it") }
        val log = store.eventLog.value
        assertThat(log.size).isAtMost(200)
        assertThat(log.last()).isEqualTo("line-249")
    }

    @Test fun `accepted ids are tracked`() {
        val store = MessageStore()
        store.markAccepted("a-1")
        assertThat(store.acceptedIds.value).contains("a-1")
    }
}
