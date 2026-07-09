package com.sankatmochan.mesh.mesh

import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothGattServer
import android.bluetooth.BluetoothGattServerCallback
import android.bluetooth.BluetoothGattService
import android.bluetooth.BluetoothManager
import android.bluetooth.le.AdvertiseCallback
import android.bluetooth.le.AdvertiseData
import android.bluetooth.le.AdvertiseSettings
import android.bluetooth.le.BluetoothLeAdvertiser
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import android.util.Log
import java.util.ArrayDeque
import java.util.concurrent.ConcurrentHashMap

/**
 * The PERIPHERAL half of a mesh node: advertises the mesh service so others can
 * find us, and runs a GATT server whose single characteristic accepts writes
 * (peers pushing envelopes to us) and sends notifications (us pushing envelopes
 * to subscribed peers). This peripheral role is the piece React Native can't do.
 */
@SuppressLint("MissingPermission")
class GattServerController(
    private val context: Context,
    private val bluetoothManager: BluetoothManager,
    private val onBytes: (ByteArray, String) -> Unit,
    private val onPeersChanged: () -> Unit,
) {
    private val adapter = bluetoothManager.adapter
    private var gattServer: BluetoothGattServer? = null
    private var advertiser: BluetoothLeAdvertiser? = null
    private lateinit var messageChar: BluetoothGattCharacteristic

    /** Peers that enabled notifications on us — our notify targets. */
    private val subscribers = ConcurrentHashMap<String, BluetoothDevice>()

    /** Per-subscriber notify queue — notifications must be drained one at a time
     *  (the next may only be sent after onNotificationSent), or they get dropped. */
    private class NotifyState {
        val queue = ArrayDeque<ByteArray>()
        var busy = false
        var retries = 0
    }
    private val notifyState = ConcurrentHashMap<String, NotifyState>()

    private val handler = Handler(Looper.getMainLooper())

    fun subscriberAddresses(): Set<String> = subscribers.keys.toSet()

    fun start() {
        val server = bluetoothManager.openGattServer(context, serverCallback)
        if (server == null) {
            Log.w(TAG, "openGattServer returned null")
            return
        }
        gattServer = server

        val service = BluetoothGattService(
            MeshUuids.SERVICE_UUID,
            BluetoothGattService.SERVICE_TYPE_PRIMARY
        )
        messageChar = BluetoothGattCharacteristic(
            MeshUuids.MESSAGE_CHAR_UUID,
            BluetoothGattCharacteristic.PROPERTY_WRITE or
                BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE or
                BluetoothGattCharacteristic.PROPERTY_NOTIFY,
            BluetoothGattCharacteristic.PERMISSION_WRITE
        )
        val cccd = BluetoothGattDescriptor(
            MeshUuids.CCCD_UUID,
            BluetoothGattDescriptor.PERMISSION_READ or BluetoothGattDescriptor.PERMISSION_WRITE
        )
        messageChar.addDescriptor(cccd)
        service.addCharacteristic(messageChar)
        server.addService(service)

        startAdvertising()
    }

    private fun startAdvertising() {
        val adv = adapter?.bluetoothLeAdvertiser
        if (adv == null) {
            Log.w(TAG, "device has no BLE advertiser")
            return
        }
        advertiser = adv
        val settings = AdvertiseSettings.Builder()
            .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
            .setConnectable(true)
            .setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_HIGH)
            .build()
        // Only the 128-bit service UUID (no device name) — keeps us inside the
        // 31-byte advertising budget.
        val data = AdvertiseData.Builder()
            .setIncludeDeviceName(false)
            .addServiceUuid(ParcelUuid(MeshUuids.SERVICE_UUID))
            .build()
        adv.startAdvertising(settings, data, advertiseCallback)
    }

    private val advertiseCallback = object : AdvertiseCallback() {
        override fun onStartFailure(errorCode: Int) {
            Log.w(TAG, "advertising failed: $errorCode")
        }
    }

    /** Queue [bytes] for every subscribed peer (optionally skipping one address). */
    fun notifyAll(bytes: ByteArray, exceptAddress: String?) {
        subscribers.keys.forEach { address ->
            if (address == exceptAddress) return@forEach
            val st = notifyState.getOrPut(address) { NotifyState() }
            synchronized(st) { st.queue.add(bytes) }
            pumpNotify(address)
        }
    }

    /** Send at most one queued notification per subscriber; the rest wait for
     *  onNotificationSent so nothing is dropped to BLE congestion. */
    private fun pumpNotify(address: String) {
        val server = gattServer ?: return
        val device = subscribers[address] ?: return
        val st = notifyState[address] ?: return
        val next: ByteArray = synchronized(st) {
            if (st.busy || st.queue.isEmpty()) return
            st.busy = true
            st.queue.poll()
        }
        val ok = sendNotification(server, device, next)
        if (!ok) {
            // Rejected NOW (usually transient congestion — onNotificationSent won't
            // fire). Re-queue at the head and retry after a short delay so we don't
            // permanently drop relayed traffic (which isn't in the sender's outbox).
            val retry = synchronized(st) {
                st.busy = false
                if (st.retries < MAX_NOTIFY_RETRIES) {
                    st.retries++
                    st.queue.addFirst(next)
                    true
                } else {
                    st.retries = 0
                    Log.w(TAG, "dropping notify to $address after $MAX_NOTIFY_RETRIES retries")
                    false
                }
            }
            if (retry) handler.postDelayed({ pumpNotify(address) }, RETRY_DELAY_MS)
        }
    }

    private fun sendNotification(server: BluetoothGattServer, device: BluetoothDevice, bytes: ByteArray): Boolean {
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                // Returns BluetoothStatusCodes.SUCCESS (0) on accepted.
                server.notifyCharacteristicChanged(device, messageChar, false, bytes) == 0
            } else {
                @Suppress("DEPRECATION")
                messageChar.value = bytes
                @Suppress("DEPRECATION")
                server.notifyCharacteristicChanged(device, messageChar, false)
            }
        } catch (e: Exception) {
            Log.w(TAG, "notify failed to ${device.address}: ${e.message}")
            false
        }
    }

    private val serverCallback = object : BluetoothGattServerCallback() {
        override fun onConnectionStateChange(device: BluetoothDevice, status: Int, newState: Int) {
            if (newState == BluetoothGatt.STATE_DISCONNECTED) {
                subscribers.remove(device.address)
                notifyState.remove(device.address)
            }
            onPeersChanged()
        }

        override fun onNotificationSent(device: BluetoothDevice, status: Int) {
            val st = notifyState[device.address] ?: return
            synchronized(st) {
                st.busy = false
                st.retries = 0
            }
            pumpNotify(device.address)
        }

        override fun onCharacteristicWriteRequest(
            device: BluetoothDevice,
            requestId: Int,
            characteristic: BluetoothGattCharacteristic,
            preparedWrite: Boolean,
            responseNeeded: Boolean,
            offset: Int,
            value: ByteArray?
        ) {
            if (characteristic.uuid == MeshUuids.MESSAGE_CHAR_UUID && value != null) {
                onBytes(value, device.address)
            }
            if (responseNeeded) {
                gattServer?.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, offset, null)
            }
        }

        override fun onDescriptorWriteRequest(
            device: BluetoothDevice,
            requestId: Int,
            descriptor: BluetoothGattDescriptor,
            preparedWrite: Boolean,
            responseNeeded: Boolean,
            offset: Int,
            value: ByteArray?
        ) {
            if (descriptor.uuid == MeshUuids.CCCD_UUID) {
                val enable = value != null && value.isNotEmpty() && value[0].toInt() != 0
                if (enable) subscribers[device.address] = device else subscribers.remove(device.address)
                onPeersChanged()
            }
            if (responseNeeded) {
                gattServer?.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, offset, null)
            }
        }
    }

    fun stop() {
        handler.removeCallbacksAndMessages(null)
        try {
            advertiser?.stopAdvertising(advertiseCallback)
        } catch (e: Exception) {
            Log.w(TAG, "stopAdvertising: ${e.message}")
        }
        try {
            gattServer?.close()
        } catch (e: Exception) {
            Log.w(TAG, "gattServer.close: ${e.message}")
        }
        subscribers.clear()
        notifyState.clear()
        advertiser = null
        gattServer = null
    }

    private companion object {
        const val TAG = "GattServer"
        const val MAX_NOTIFY_RETRIES = 5
        const val RETRY_DELAY_MS = 25L
    }
}
