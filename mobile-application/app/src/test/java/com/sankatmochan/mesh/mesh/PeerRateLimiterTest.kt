package com.sankatmochan.mesh.mesh

import com.google.common.truth.Truth.assertThat
import org.junit.Test

/** Token-bucket behaviour, driven by a fake clock so no real time passes. */
class PeerRateLimiterTest {

    private var now = 0L
    private fun limiter(rate: Double, burst: Int) =
        PeerRateLimiter(ratePerSec = rate, burst = burst, clock = { now })

    @Test fun `allows up to the burst immediately then drops`() {
        val rl = limiter(rate = 10.0, burst = 5)
        repeat(5) { assertThat(rl.allow("peerA")).isTrue() }
        assertThat(rl.allow("peerA")).isFalse()
    }

    @Test fun `refills over time at the configured rate`() {
        val rl = limiter(rate = 10.0, burst = 5)
        repeat(5) { rl.allow("peerA") }        // drain
        assertThat(rl.allow("peerA")).isFalse()
        now += 200                              // 0.2s * 10/s = 2 tokens
        assertThat(rl.allow("peerA")).isTrue()
        assertThat(rl.allow("peerA")).isTrue()
        assertThat(rl.allow("peerA")).isFalse()
    }

    @Test fun `refill never exceeds the burst ceiling`() {
        val rl = limiter(rate = 10.0, burst = 5)
        repeat(5) { rl.allow("peerA") }
        now += 10_000                           // huge gap
        // Bucket caps at burst=5, not 100k tokens.
        repeat(5) { assertThat(rl.allow("peerA")).isTrue() }
        assertThat(rl.allow("peerA")).isFalse()
    }

    @Test fun `peers are throttled independently`() {
        val rl = limiter(rate = 10.0, burst = 2)
        assertThat(rl.allow("A")).isTrue()
        assertThat(rl.allow("A")).isTrue()
        assertThat(rl.allow("A")).isFalse()
        // A different peer has its own full bucket.
        assertThat(rl.allow("B")).isTrue()
        assertThat(rl.allow("B")).isTrue()
        assertThat(rl.allow("B")).isFalse()
    }

    @Test fun `bucket map is bounded by maxPeers`() {
        val rl = PeerRateLimiter(ratePerSec = 10.0, burst = 1, maxPeers = 4, clock = { now })
        // Churn through many addresses; the map must not grow without bound. We can't read the
        // map size directly, but eviction of an old peer means it starts fresh (full) again.
        repeat(100) { rl.allow("addr-$it") }
        // The very first address was evicted long ago, so it gets a fresh bucket.
        assertThat(rl.allow("addr-0")).isTrue()
    }

    @Test fun `a clock that goes backwards never grants extra tokens`() {
        val rl = limiter(rate = 10.0, burst = 3)
        repeat(3) { rl.allow("A") }
        now -= 5_000                            // clock skew backwards
        assertThat(rl.allow("A")).isFalse()     // elapsed is clamped to >= 0
    }
}
