package com.sankatmochan.mesh.mesh

/**
 * A per-peer token-bucket rate limiter — a DoS backstop on the mesh ingress path.
 *
 * Every byte arriving from a peer is untrusted (CLAUDE.md #8). Each accepted packet costs a
 * decode plus, for a fresh id, a re-broadcast to every *other* peer — so one flooding peer is
 * amplified across the whole mesh and can burn the channel, CPU and battery of every node it
 * reaches. This limiter caps the *sustained* rate any single peer can push through, while a
 * generous burst still lets legitimate bursty traffic (a voice clip is a dozen-plus frames
 * back-to-back, plus relayed traffic) pass untouched.
 *
 * The limits are deliberately well above any honest node's output: this is a floodgate, not a
 * flow-control mechanism. Real mesh delivery still relies on the queues in the GATT
 * controllers; this only sheds the pathological case.
 *
 * Thread-safe. [clock] is injectable so the behaviour is unit-testable without real time.
 */
class PeerRateLimiter(
    private val ratePerSec: Double = DEFAULT_RATE_PER_SEC,
    private val burst: Int = DEFAULT_BURST,
    private val maxPeers: Int = DEFAULT_MAX_PEERS,
    private val clock: () -> Long = { android.os.SystemClock.elapsedRealtime() },
) {
    init {
        require(ratePerSec > 0) { "ratePerSec must be positive" }
        require(burst > 0) { "burst must be positive" }
        require(maxPeers > 0) { "maxPeers must be positive" }
    }

    private class Bucket(var tokens: Double, var lastRefillMs: Long)

    // Bounded so a peer churning through many (possibly spoofed) addresses can't grow this map
    // without limit — the same unbounded-memory concern [BoundedIdSet] guards. Eldest peer's
    // bucket is evicted; it simply starts fresh (full) if it comes back.
    private val buckets = object : LinkedHashMap<String, Bucket>(64, 0.75f, false) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, Bucket>): Boolean =
            size > maxPeers
    }

    /**
     * Charge one packet from [peer]. Returns true if it is within budget (caller should process
     * it), false if the peer is over its rate and the packet must be dropped.
     */
    @Synchronized
    fun allow(peer: String): Boolean {
        val now = clock()
        val bucket = buckets[peer] ?: Bucket(burst.toDouble(), now).also { buckets[peer] = it }
        // Refill proportionally to elapsed time, capped at the burst size.
        val elapsedSec = (now - bucket.lastRefillMs).coerceAtLeast(0L) / 1000.0
        bucket.tokens = (bucket.tokens + elapsedSec * ratePerSec).coerceAtMost(burst.toDouble())
        bucket.lastRefillMs = now
        return if (bucket.tokens >= 1.0) {
            bucket.tokens -= 1.0
            true
        } else {
            false
        }
    }

    @Synchronized
    fun forget(peer: String) {
        buckets.remove(peer)
    }

    private companion object {
        /** Sustained packets/sec allowed per peer. A voice clip's dozen-plus frames and normal
         *  relayed traffic sit far under this; only a deliberate flood exceeds it. */
        const val DEFAULT_RATE_PER_SEC = 120.0
        /** Momentary allowance so a legitimate burst (a whole clip at once) isn't clipped. */
        const val DEFAULT_BURST = 240
        const val DEFAULT_MAX_PEERS = 64
    }
}
