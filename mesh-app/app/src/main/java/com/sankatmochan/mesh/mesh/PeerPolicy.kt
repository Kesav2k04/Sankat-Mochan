package com.sankatmochan.mesh.mesh

/**
 * Decides which discovered peripherals this node's CENTRAL half may connect to.
 *
 * Why this exists: every phone both advertises the mesh service *and* scans for it,
 * so two phones sitting on the same table will always find each other and link up
 * directly over BLE. When the point of the demo is that a message crossed the
 * long-range LoRa bridge, that direct hop silently steals the traffic — the SOS
 * arrives, and the radios never carry a byte.
 *
 * [DenyAll] switches the central half off without touching the peripheral half. The
 * phone keeps advertising, so the Pi's LoRa gateway (a BLE central) can still connect
 * to us, subscribe to notifications, and write envelopes back. The result is that the
 * ONLY route off this phone is the gateway's radio.
 *
 * Note this is a per-phone setting: it stops *us* dialling out. Two phones must both
 * enable it, or the other one will still connect inbound to us.
 */
sealed interface PeerPolicy {

    fun allows(address: String): Boolean

    /** Normal mesh behaviour: peer with anything advertising the mesh service. */
    data object AllowAll : PeerPolicy {
        override fun allows(address: String): Boolean = true
    }

    /** Dial out to nobody. We stay reachable as a peripheral. */
    data object DenyAll : PeerPolicy {
        override fun allows(address: String): Boolean = false
    }

    /** Dial out only to these MACs — e.g. a known relay phone, but not the other endpoint. */
    data class Allowlist(val addresses: Set<String>) : PeerPolicy {
        private val normalised: Set<String> = addresses.mapTo(HashSet()) { it.uppercase() }
        override fun allows(address: String): Boolean = address.uppercase() in normalised
    }
}
