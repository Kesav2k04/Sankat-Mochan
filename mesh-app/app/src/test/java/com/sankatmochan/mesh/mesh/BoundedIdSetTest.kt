package com.sankatmochan.mesh.mesh

import com.google.common.truth.Truth.assertThat
import org.junit.Test

/** Unit tests for the dedup set's first-seen semantics and its memory-bounding eviction. */
class BoundedIdSetTest {

    @Test fun `add returns true only the first time an id is seen`() {
        val set = BoundedIdSet()
        assertThat(set.add("a-1")).isTrue()
        assertThat(set.add("a-1")).isFalse()
        assertThat(set.add("a-2")).isTrue()
    }

    @Test fun `contains reflects membership`() {
        val set = BoundedIdSet()
        assertThat("x" in set).isFalse()
        set.add("x")
        assertThat("x" in set).isTrue()
    }

    @Test fun `size never exceeds capacity`() {
        val set = BoundedIdSet(capacity = 10)
        repeat(1_000) { set.add("id-$it") }
        assertThat(set.size()).isEqualTo(10)
    }

    @Test fun `eldest id is evicted once capacity is exceeded`() {
        val set = BoundedIdSet(capacity = 3)
        set.add("1"); set.add("2"); set.add("3")
        set.add("4") // evicts "1"
        assertThat("1" in set).isFalse()
        assertThat("2" in set).isTrue()
        assertThat("4" in set).isTrue()
        // A re-seen-but-evicted id counts as new again — acceptable under a flood.
        assertThat(set.add("1")).isTrue()
    }

    @Test fun `re-seeing an id refreshes its recency (access-order LRU)`() {
        val set = BoundedIdSet(capacity = 3)
        set.add("1"); set.add("2"); set.add("3")
        set.add("1") // duplicate; moves "1" to the newest slot, so "2" is now eldest
        set.add("4") // evicts the least-recently-seen, which is "2"
        assertThat("2" in set).isFalse()
        assertThat("1" in set).isTrue()
        assertThat("4" in set).isTrue()
    }

    @Test fun `clear empties the set`() {
        val set = BoundedIdSet()
        set.add("a"); set.add("b")
        set.clear()
        assertThat(set.size()).isEqualTo(0)
        assertThat(set.add("a")).isTrue()
    }

    @Test(expected = IllegalArgumentException::class)
    fun `capacity must be positive`() {
        BoundedIdSet(capacity = 0)
    }
}
