package com.sankatmochan.mesh.mesh

import java.util.UUID

/**
 * Fixed 128-bit UUIDs that identify the Sankat-Mochan mesh over BLE.
 *
 * Every node advertises [SERVICE_UUID] and exposes a single [MESSAGE_CHAR_UUID]
 * characteristic that is both WRITE (a central pushes an envelope to us) and
 * NOTIFY (we push envelopes to subscribed centrals). One characteristic carries
 * traffic in both directions over a single GATT link.
 */
object MeshUuids {
    val SERVICE_UUID: UUID = UUID.fromString("6b1d0a01-4c2f-4b9c-9d2f-2a7c5e3f1a01")
    val MESSAGE_CHAR_UUID: UUID = UUID.fromString("6b1d0a02-4c2f-4b9c-9d2f-2a7c5e3f1a01")

    /** Standard Client Characteristic Configuration Descriptor - enables notifications. */
    val CCCD_UUID: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
}
