package com.sankatmochan.mesh.mesh

import android.annotation.SuppressLint
import android.bluetooth.BluetoothManager
import android.content.Context
import android.util.Log
import com.sankatmochan.mesh.model.MsgType
import com.sankatmochan.mesh.model.SosMessage
import android.os.Handler
import android.os.Looper
import com.sankatmochan.mesh.model.VoiceChunk
import com.sankatmochan.mesh.model.VoiceFrame
import com.sankatmochan.mesh.model.VoiceNack
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlin.random.Random

/** Which person this node is playing in the demo. Transport is identical for all. */
enum class MeshRole { VICTIM, RESPONDER, RELAY }

/**
 * Orchestrates the two BLE halves (peripheral + central) into one mesh node and
 * owns the message logic: dedup, loop-free store-and-forward, and the honest
 * victim status ladder (Sending → reached control room → help on the way).
 *
 * Every node both advertises/serves AND scans/connects, so any node can relay —
 * a 3rd phone dropped in between victim and responder needs zero code changes.
 */
@SuppressLint("MissingPermission")
class BleMeshService(context: Context) {

    val store = MessageStore()
    val voiceClips = VoiceClipStore(context)

    /** Short per-session node id, e.g. "a3f9". Prefixes every message id. */
    val nodeId: String = "%04x".format(Random.nextInt(0x10000))

    var role: MeshRole = MeshRole.RELAY
        private set

    private var seq = 0
    private var voiceSeq = 0
    private var running = false

    private val handler = Handler(Looper.getMainLooper())
    /** Clips we originated, kept so we can honour a resend request. seq -> chunks. */
    private val sentClips = LinkedHashMap<Int, List<VoiceChunk>>()
    /** How many resend requests we have already sent for a clip we are receiving. */
    private val nackAttempts = HashMap<String, Int>()

    // Messages THIS node originated, kept so we can re-send them to any peer that
    // connects after we first broadcast (fixes the "SOS sent before the responder
    // was subscribed is lost forever" race). Receivers dedup, so re-sends are safe.
    private val outbox = java.util.Collections.synchronizedList(ArrayList<SosMessage>())
    private val knownPeers = java.util.Collections.synchronizedSet(HashSet<String>())

    private companion object {
        const val TAG = "BleMeshService"
        const val OUTBOX_CAP = 20
        /** How long a clip must be silent before we conclude a piece is really lost.
         *  Longer than the airtime of a few frames, shorter than a rescuer's patience. */
        const val NACK_QUIET_MS = 3_000L
        const val SENT_CLIPS_CAP = 4
    }

    /**
     * When true, this phone stops dialling out to other phones. It keeps advertising,
     * so the Pi's LoRa gateway (a BLE central) still connects inbound — which makes the
     * gateway's radio the only way a message can leave this device. Turn it on for the
     * phone-to-phone-over-LoRa demo; leave it off for the pure BLE mesh demo.
     *
     * Both endpoint phones must enable it. It stops us dialling them; it cannot stop
     * them dialling us.
     */
    private val _loraOnly = MutableStateFlow(false)
    val loraOnly: StateFlow<Boolean> = _loraOnly.asStateFlow()

    private fun peerPolicy(): PeerPolicy =
        if (_loraOnly.value) PeerPolicy.DenyAll else PeerPolicy.AllowAll

    private val bluetoothManager =
        context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager

    private val server = GattServerController(context, bluetoothManager, ::onBytes, ::recomputePeers)
    private val scanner =
        GattScannerController(context, bluetoothManager, ::onBytes, ::recomputePeers, ::peerPolicy)

    fun isBluetoothReady(): Boolean = bluetoothManager.adapter?.isEnabled == true

    /** Flip LoRa-only mode. Drops any phone links we already hold. */
    fun setLoraOnly(enabled: Boolean) {
        if (_loraOnly.value == enabled) return
        _loraOnly.value = enabled
        scanner.enforcePolicy()
        store.log(
            if (enabled) "LoRa-only ON — ignoring nearby phones; traffic must cross the gateway radio"
            else "LoRa-only OFF — peering directly with nearby phones again"
        )
    }

    fun start(role: MeshRole) {
        this.role = role
        if (running) return
        // The role goes into the advertisement, so the gateway can route by it.
        server.start(role, nodeId)
        scanner.start()
        running = true
        store.log("Mesh started as $role · node $nodeId")
    }

    fun stop() {
        if (!running) return
        handler.removeCallbacksAndMessages(null)
        scanner.stop()
        server.stop()
        running = false
        store.setPeerCount(0)
        store.log("Mesh stopped")
    }

    private fun nextId(): String = "$nodeId-${seq++}"

    private fun recomputePeers() {
        // Union of addresses across both roles → one physical peer counts once.
        val current = server.subscriberAddresses() + scanner.readyAddresses()
        store.setPeerCount(current.size)

        val added = synchronized(knownPeers) {
            val newOnes = current - knownPeers
            knownPeers.clear()
            knownPeers.addAll(current)
            newOnes
        }
        if (added.isNotEmpty()) flushOutbox()
    }

    private fun rememberOutbound(msg: SosMessage) {
        synchronized(outbox) {
            outbox.add(msg)
            while (outbox.size > OUTBOX_CAP) outbox.removeAt(0)
        }
    }

    /** Re-broadcast everything we've originated — called when a new peer appears. */
    private fun flushOutbox() {
        val snapshot = synchronized(outbox) { outbox.toList() }
        if (snapshot.isEmpty()) return
        snapshot.forEach { broadcast(it, exceptAddress = null) }
        store.log("Re-sent ${snapshot.size} pending message(s) to new peer")
    }

    // --- Outgoing (originated locally) ------------------------------------

    fun sendSos(
        category: String,
        urgency: Int,
        gist: String,
        lang: String,
        locationHint: String,
        lat: Double? = null,
        lng: Double? = null
    ) {
        val msg = SosMessage(
            id = nextId(),
            type = MsgType.SOS,
            origin = nodeId,
            urgency = urgency.coerceIn(1, 5),
            category = category,
            locationHint = locationHint,
            gist = gist,
            lang = lang,
            lat = lat,
            lng = lng,
            ts = System.currentTimeMillis(),
            hops = 0
        )
        store.markSeen(msg.id)
        store.addSent(msg)
        store.log("SOS sent [${msg.urgency}] ${msg.category}: ${msg.gist}")
        rememberOutbound(msg)
        broadcast(msg, exceptAddress = null)
    }

    /** Responder accepts a SOS → tells the victim help is coming. */
    fun accept(sos: SosMessage) {
        store.markAccepted(sos.id)
        val ack = SosMessage(
            id = nextId(),
            type = MsgType.ACCEPTED,
            origin = nodeId,
            refId = sos.id,
            gist = "Help is on the way",
            lang = sos.lang,
            ts = System.currentTimeMillis()
        )
        store.markSeen(ack.id)
        store.log("Accepted ${sos.id} — responder en route")
        rememberOutbound(ack)
        broadcast(ack, exceptAddress = null)
    }

    // --- Incoming ---------------------------------------------------------

    /** Called by BOTH controllers whenever raw bytes arrive from a peer. */
    private fun onBytes(bytes: ByteArray, fromAddress: String) {
        // A JSON envelope always starts '{'; a voice frame starts 0xA5, which is not a
        // legal UTF-8 lead byte. The two can never be confused.
        if (VoiceChunk.looksLikeVoice(bytes)) {
            onVoiceChunk(bytes, fromAddress)
            return
        }
        val msg = SosMessage.decode(bytes)
        if (msg == null) {
            store.log("Dropped malformed packet from $fromAddress")
            return
        }
        if (!store.markSeen(msg.id)) return // dedup — also the store-and-forward loop guard
        handle(msg, fromAddress)
    }

    private fun onVoiceChunk(bytes: ByteArray, fromAddress: String) {
        val frame = VoiceChunk.decode(bytes)
        if (frame == null) {
            store.log("Dropped malformed voice packet from $fromAddress")
            return
        }
        // Dedup on the frame id, not the clip id — otherwise the first chunk to arrive
        // would suppress all its siblings. The id carries `attempt`, so a retransmission
        // is a new id and survives dedup; only a looping copy is dropped.
        if (!store.markSeen(frame.id)) return

        when (frame) {
            is VoiceChunk -> {
                voiceClips.accept(frame)
                if (frame.index == 0 && frame.attempt == 0) {
                    store.log("Voice message ${frame.clipId} incoming (${frame.total} pieces, hop ${frame.hops})")
                }
                scheduleNack(frame.clipId, frame.origin, frame.seq, frame.total)
                broadcastBytes(frame.bumped().encode(), exceptAddress = fromAddress)
            }
            is VoiceNack -> {
                if (frame.clipOrigin == nodeId) resendMissing(frame)
                else broadcastBytes(frame.bumped().encode(), exceptAddress = fromAddress)
            }
        }
    }

    /**
     * Ask for the pieces that never arrived.
     *
     * Armed on every chunk and pushed back each time, so it fires only once the clip has
     * gone quiet — a NACK sent mid-transfer would ask for chunks that are still on air and
     * waste the channel repeating them.
     */
    private fun scheduleNack(clipId: String, clipOrigin: String, seq: Int, total: Int) {
        if (clipOrigin == nodeId) return          // never NACK our own recording
        handler.removeCallbacksAndMessages(clipId)
        handler.postAtTime({
            val missing = voiceClips.missingOf(clipId)
            if (missing.isEmpty()) {
                nackAttempts.remove(clipId)
                return@postAtTime
            }
            val attempt = nackAttempts.getOrDefault(clipId, 0)
            if (attempt >= VoiceChunk.MAX_ATTEMPTS - 1) {
                store.log("Voice message $clipId: gave up after $attempt resend requests, " +
                    "${missing.size} piece(s) never arrived")
                return@postAtTime
            }
            nackAttempts[clipId] = attempt + 1
            val nack = VoiceNack(nodeId, clipOrigin, seq, total, missing, attempt = attempt)
            store.markSeen(nack.id)
            store.log("Voice message $clipId: asking for ${missing.size} missing piece(s)")
            broadcastBytes(nack.encode(), exceptAddress = null)
            // Ask again if the repair itself gets lost.
            scheduleNack(clipId, clipOrigin, seq, total)
        }, clipId, android.os.SystemClock.uptimeMillis() + NACK_QUIET_MS)
    }

    /** A receiver is missing pieces of a clip we recorded. Send exactly those, again. */
    private fun resendMissing(nack: VoiceNack) {
        val chunks = synchronized(sentClips) { sentClips[nack.seq] }
        if (chunks == null) {
            store.log("Cannot honour resend request for ${nack.clipId} — clip no longer held")
            return
        }
        val attempt = minOf(nack.attempt + 1, VoiceChunk.MAX_ATTEMPTS - 1)
        val wanted = nack.missing.filter { it < chunks.size }
        store.log("Resending ${wanted.size} piece(s) of ${nack.clipId} (attempt $attempt)")
        wanted.forEach { i ->
            val retry = chunks[i].copy(attempt = attempt, hops = 0)
            store.markSeen(retry.id)
            broadcastBytes(retry.encode(), exceptAddress = null)
        }
    }

    /**
     * Send a recorded clip. Every chunk is marked seen locally first, so the copy that
     * loops back from a relay is dropped rather than re-broadcast.
     */
    fun sendVoice(clip: ByteArray, codec: Int) {
        val chunks = try {
            VoiceChunk.split(nodeId, voiceSeq++, clip, codec)
        } catch (e: IllegalArgumentException) {
            store.log("Voice message too long to send")
            return
        }
        store.log("Sending voice message: ${clip.size} bytes in ${chunks.size} pieces")
        // Hold on to it: a receiver that loses a frame will ask for it by index.
        synchronized(sentClips) {
            sentClips[chunks.first().seq] = chunks
            while (sentClips.size > SENT_CLIPS_CAP) {
                sentClips.remove(sentClips.keys.first())
            }
        }
        chunks.forEach { chunk ->
            store.markSeen(chunk.id)
            broadcastBytes(chunk.encode(), exceptAddress = null)
        }
    }

    private fun handle(msg: SosMessage, fromAddress: String) {
        when (msg.type) {
            MsgType.SOS -> {
                store.addReceivedSos(msg)
                store.log("SOS in [${msg.urgency}] ${msg.category}: ${msg.gist} (hop ${msg.hops})")
                // If we're the control room, acknowledge delivery back to the victim.
                if (role == MeshRole.RESPONDER) {
                    val delivered = SosMessage(
                        id = nextId(),
                        type = MsgType.DELIVERED,
                        origin = nodeId,
                        refId = msg.id,
                        gist = "reached control room",
                        lang = msg.lang,
                        ts = System.currentTimeMillis()
                    )
                    store.markSeen(delivered.id)
                    // NOT added to the outbox: DELIVERED is a transient stage-1 hint.
                    // Only SOS (needs re-delivery) and ACCEPTED (final status) are
                    // kept for re-send on reconnect, which keeps outbox churn low.
                    broadcast(delivered, exceptAddress = null)
                }
            }
            MsgType.DELIVERED -> msg.refId?.let {
                store.updateSentStatus(it, stage = 1, text = "Message reached the control room")
                store.log("Delivery ack for $it")
            }
            MsgType.ACCEPTED -> msg.refId?.let {
                store.updateSentStatus(it, stage = 2, text = "Help is on the way")
                store.log("Help-on-the-way for $it")
            }
        }
        // Store-and-forward: pass it onward to every OTHER peer. The markSeen
        // guard above means each node forwards a given id at most once → no loops.
        broadcast(msg.copy(hops = (msg.hops + 1).coerceAtMost(15)), exceptAddress = fromAddress)
    }

    private fun broadcast(msg: SosMessage, exceptAddress: String?) {
        broadcastBytes(msg.encode(), exceptAddress)
    }

    /** Both BLE halves. The peripheral half is what keeps working in LoRa-only mode,
     *  where the central half is deliberately switched off. */
    private fun broadcastBytes(bytes: ByteArray, exceptAddress: String?) {
        server.notifyAll(bytes, exceptAddress)
        scanner.writeToAll(bytes, exceptAddress)
    }
}
