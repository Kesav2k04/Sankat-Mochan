package com.sankatmochan.mesh.mesh

import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothManager
import android.bluetooth.le.BluetoothLeScanner
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import android.util.Log
import java.util.ArrayDeque
import java.util.concurrent.ConcurrentHashMap

/**
 * The CENTRAL half of a mesh node: scans for peers advertising the mesh service,
 * connects, enables notifications, and writes outgoing envelopes to them. A tiny
 * per-connection write queue serialises GATT operations (Android allows only one
 * outstanding op per link at a time).
 */
@SuppressLint("MissingPermission")
class GattScannerController(
    private val context: Context,
    private val bluetoothManager: BluetoothManager,
    private val onBytes: (ByteArray, String) -> Unit,
    private val onPeersChanged: () -> Unit,
    /** Read fresh on every scan hit so a policy change takes effect immediately. */
    private val peerPolicy: () -> PeerPolicy = { PeerPolicy.AllowAll },
) {
    private val adapter = bluetoothManager.adapter
    private var scanner: BluetoothLeScanner? = null

    private class Conn(val gatt: BluetoothGatt) {
        var characteristic: BluetoothGattCharacteristic? = null
        var ready = false
        val queue = ArrayDeque<ByteArray>()
        var busy = false
        var retries = 0
    }

    private val connections = ConcurrentHashMap<String, Conn>()
    private val connecting = ConcurrentHashMap.newKeySet<String>()
    private val handler = Handler(Looper.getMainLooper())

    fun readyAddresses(): Set<String> =
        connections.filterValues { it.ready }.keys.toSet()

    fun start() {
        val s = adapter?.bluetoothLeScanner
        if (s == null) {
            Log.w(TAG, "device has no BLE scanner")
            return
        }
        scanner = s
        val filter = ScanFilter.Builder()
            .setServiceUuid(ParcelUuid(MeshUuids.SERVICE_UUID))
            .build()
        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build()
        s.startScan(listOf(filter), settings, scanCallback)
    }

    private val scanCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            val address = result.device.address
            if (!peerPolicy().allows(address)) return
            if (connections.containsKey(address) || !connecting.add(address)) return
            Log.d(TAG, "connecting to $address")
            result.device.connectGatt(context, false, gattCallback, BluetoothDevice.TRANSPORT_LE)
        }

        override fun onScanFailed(errorCode: Int) {
            Log.w(TAG, "scan failed: $errorCode")
        }
    }

    private val gattCallback = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
            val address = gatt.device.address
            when (newState) {
                BluetoothGatt.STATE_CONNECTED -> {
                    connections[address] = Conn(gatt)
                    gatt.requestMtu(247)
                }
                BluetoothGatt.STATE_DISCONNECTED -> {
                    connections.remove(address)
                    connecting.remove(address)
                    try { gatt.close() } catch (_: Exception) {}
                    onPeersChanged()
                }
            }
        }

        override fun onMtuChanged(gatt: BluetoothGatt, mtu: Int, status: Int) {
            gatt.discoverServices()
        }

        override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
            val conn = connections[gatt.device.address] ?: return
            val ch = gatt.getService(MeshUuids.SERVICE_UUID)
                ?.getCharacteristic(MeshUuids.MESSAGE_CHAR_UUID)
            if (ch == null) {
                Log.w(TAG, "peer ${gatt.device.address} missing mesh characteristic")
                return
            }
            conn.characteristic = ch
            gatt.setCharacteristicNotification(ch, true)
            val cccd = ch.getDescriptor(MeshUuids.CCCD_UUID)
            if (cccd != null) {
                writeCccdEnable(gatt, cccd)
            } else {
                conn.ready = true
                onPeersChanged()
            }
        }

        override fun onDescriptorWrite(gatt: BluetoothGatt, descriptor: BluetoothGattDescriptor, status: Int) {
            val conn = connections[gatt.device.address] ?: return
            conn.ready = true
            onPeersChanged()
            pump(gatt.device.address)
        }

        // API 33+ delivers the value directly.
        override fun onCharacteristicChanged(
            gatt: BluetoothGatt,
            characteristic: BluetoothGattCharacteristic,
            value: ByteArray
        ) {
            if (characteristic.uuid == MeshUuids.MESSAGE_CHAR_UUID) {
                onBytes(value, gatt.device.address)
            }
        }

        // API <33 path: read the value off the characteristic.
        @Deprecated("Deprecated in API 33")
        @Suppress("DEPRECATION")
        override fun onCharacteristicChanged(
            gatt: BluetoothGatt,
            characteristic: BluetoothGattCharacteristic
        ) {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU &&
                characteristic.uuid == MeshUuids.MESSAGE_CHAR_UUID
            ) {
                characteristic.value?.let { onBytes(it, gatt.device.address) }
            }
        }

        override fun onCharacteristicWrite(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, status: Int) {
            val conn = connections[gatt.device.address] ?: return
            synchronized(conn) {
                conn.busy = false
                conn.retries = 0
            }
            pump(gatt.device.address)
        }
    }

    private fun writeCccdEnable(gatt: BluetoothGatt, cccd: BluetoothGattDescriptor) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            gatt.writeDescriptor(cccd, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
        } else {
            @Suppress("DEPRECATION")
            cccd.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
            @Suppress("DEPRECATION")
            gatt.writeDescriptor(cccd)
        }
    }

    /**
     * Re-apply [peerPolicy] to links we already hold. Refusing *new* connections is
     * not enough: when the policy tightens mid-session (the operator flips LoRa-only
     * on), any phone we already dialled would keep relaying and quietly bypass the
     * radio hop. Drop those links now. Peers that connected *to us* are unaffected —
     * they live in GattServerController, which is exactly what the gateway uses.
     */
    fun enforcePolicy() {
        val policy = peerPolicy()
        connections.forEach { (address, conn) ->
            if (policy.allows(address)) return@forEach
            Log.d(TAG, "policy now forbids $address — disconnecting")
            try { conn.gatt.disconnect() } catch (_: Exception) {}
            try { conn.gatt.close() } catch (_: Exception) {}
            connections.remove(address)
            connecting.remove(address)
        }
        onPeersChanged()
    }

    /** Queue [bytes] for every ready peer (optionally skipping one address). */
    fun writeToAll(bytes: ByteArray, exceptAddress: String?) {
        connections.forEach { (address, conn) ->
            if (address == exceptAddress || !conn.ready) return@forEach
            synchronized(conn) { conn.queue.add(bytes) }
            pump(address)
        }
    }

    private fun pump(address: String) {
        val conn = connections[address] ?: return
        val gatt = conn.gatt
        val ch = conn.characteristic ?: return
        val next: ByteArray? = synchronized(conn) {
            if (conn.busy || conn.queue.isEmpty()) null
            else {
                conn.busy = true
                conn.queue.poll()
            }
        }
        if (next == null) return
        val accepted: Boolean = try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                // Returns BluetoothStatusCodes.SUCCESS (0) when the write is accepted.
                gatt.writeCharacteristic(ch, next, BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) == 0
            } else {
                @Suppress("DEPRECATION")
                ch.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
                @Suppress("DEPRECATION")
                ch.value = next
                @Suppress("DEPRECATION")
                gatt.writeCharacteristic(ch)
            }
        } catch (e: Exception) {
            Log.w(TAG, "write failed to $address: ${e.message}")
            false
        }
        if (!accepted) {
            // Rejected synchronously (usually transient congestion — onCharacteristicWrite
            // won't fire). Re-queue at the head and retry after a short delay so relayed
            // writes (not in the sender's outbox) aren't permanently dropped. Bounded so
            // a persistently-failing link can never stall the queue forever.
            val retry = synchronized(conn) {
                conn.busy = false
                if (conn.retries < MAX_WRITE_RETRIES) {
                    conn.retries++
                    conn.queue.addFirst(next)
                    true
                } else {
                    conn.retries = 0
                    Log.w(TAG, "dropping write to $address after $MAX_WRITE_RETRIES retries")
                    false
                }
            }
            if (retry) handler.postDelayed({ pump(address) }, RETRY_DELAY_MS) else pump(address)
        }
    }

    fun stop() {
        handler.removeCallbacksAndMessages(null)
        try {
            scanner?.stopScan(scanCallback)
        } catch (e: Exception) {
            Log.w(TAG, "stopScan: ${e.message}")
        }
        connections.values.forEach { conn ->
            try { conn.gatt.disconnect() } catch (_: Exception) {}
            try { conn.gatt.close() } catch (_: Exception) {}
        }
        connections.clear()
        connecting.clear()
        scanner = null
    }

    private companion object {
        const val TAG = "GattScanner"
        const val MAX_WRITE_RETRIES = 5
        const val RETRY_DELAY_MS = 25L
    }
}
