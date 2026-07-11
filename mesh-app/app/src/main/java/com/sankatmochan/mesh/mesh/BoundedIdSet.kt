package com.sankatmochan.mesh.mesh

/**
 * Insertion-ordered set of message ids with a hard capacity, used for mesh dedup.
 *
 * Dedup is what makes store-and-forward loop-free — a node forwards a given id at most once.
 * A naive unbounded set is, however, a memory-exhaustion DoS: every incoming mesh packet is
 * untrusted (CLAUDE.md #8), and a buggy or hostile peer that streams packets with ever-changing
 * ids would grow the set without limit until this safety-critical app is killed by the OS.
 *
 * Capacity-bounding trades "remember every id forever" for "remember the most recent
 * [capacity] ids": once the cap is hit, the oldest id is evicted. [capacity] is set far above
 * any real session's traffic, so eviction only ever happens under a flood — and by the time a
 * flood has pushed millions of ids through, re-processing one long-evicted id is a non-issue
 * next to the flood itself (which the [PeerRateLimiter] is separately throttling).
 *
 * This mirrors the Pi gateway's `_mark_seen` (pi-code/node.py): an access-ordered LRU where a
 * *re-seen* id is moved back to the newest slot. Keeping both mesh endpoints' dedup semantics
 * identical means a message that keeps looping stays "seen" (and keeps being dropped) on either
 * side rather than aging out and being re-forwarded.
 *
 * Thread-safe: reached from the BLE binder threads via [MessageStore.markSeen].
 */
class BoundedIdSet(private val capacity: Int = DEFAULT_CAPACITY) {

    init { require(capacity > 0) { "capacity must be positive" } }

    // accessOrder=true → a duplicate `add` (put on an existing key) moves that id back to the
    // newest slot, so a persistently-looping id never ages out while it is still circulating.
    // Eviction always drops the *least-recently-seen* id once the cap is exceeded.
    private val map = object : LinkedHashMap<String, Unit>(INITIAL_CAPACITY, LOAD_FACTOR, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, Unit>): Boolean =
            size > capacity
    }

    /** Returns true the FIRST time [id] is seen; false thereafter (until it is evicted). */
    @Synchronized
    fun add(id: String): Boolean = map.put(id, Unit) == null

    @Synchronized
    operator fun contains(id: String): Boolean = map.containsKey(id)

    @Synchronized
    fun size(): Int = map.size

    @Synchronized
    fun clear() = map.clear()

    private companion object {
        /** ~8k ids ≈ a few hundred kB of Strings — negligible, and orders of magnitude past any
         *  real demo's message count, so honest traffic never triggers an eviction. */
        const val DEFAULT_CAPACITY = 8192
        const val INITIAL_CAPACITY = 512
        const val LOAD_FACTOR = 0.75f
    }
}
