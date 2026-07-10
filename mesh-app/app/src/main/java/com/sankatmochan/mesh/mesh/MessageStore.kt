package com.sankatmochan.mesh.mesh

import com.sankatmochan.mesh.model.SosMessage
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

/** A SOS this device originated, plus the latest status we've heard back. */
data class SentSos(
    val message: SosMessage,
    val stage: Int,        // 0 sending, 1 reached control room, 2 help on the way
    val statusText: String
)

/**
 * In-memory state for the UI plus dedup bookkeeping for the mesh. Deliberately
 * simple (no DB) — a phone reboot clears it, which is fine for the demo. The
 * seen-id set is what makes store-and-forward loop-free.
 */
class MessageStore {

    private val seenIds = HashSet<String>()

    private val _receivedSos = MutableStateFlow<List<SosMessage>>(emptyList())
    val receivedSos: StateFlow<List<SosMessage>> = _receivedSos.asStateFlow()

    private val _sent = MutableStateFlow<List<SentSos>>(emptyList())
    val sent: StateFlow<List<SentSos>> = _sent.asStateFlow()

    private val _eventLog = MutableStateFlow<List<String>>(emptyList())
    val eventLog: StateFlow<List<String>> = _eventLog.asStateFlow()

    private val _peerCount = MutableStateFlow(0)
    val peerCount: StateFlow<Int> = _peerCount.asStateFlow()

    /** Ids of SOS messages this responder has accepted. Lives here, not in a
     *  composable's `remember`, so it survives rotation and screen re-entry. */
    private val _acceptedIds = MutableStateFlow<Set<String>>(emptySet())
    val acceptedIds: StateFlow<Set<String>> = _acceptedIds.asStateFlow()

    /** Returns true the FIRST time an id is seen; false thereafter (dedup). */
    @Synchronized
    fun markSeen(id: String): Boolean = seenIds.add(id)

    fun markAccepted(sosId: String) {
        _acceptedIds.update { it + sosId }
    }

    // These run on BLE binder threads; update{} is atomic (no lost-update race).
    fun addReceivedSos(msg: SosMessage) {
        _receivedSos.update { current ->
            // Most urgent first, then newest — a fresh CRITICAL must never sort
            // below a stale one the responder has already read past.
            (current + msg).distinctBy { it.id }
                .sortedWith(compareByDescending<SosMessage> { it.urgency }.thenByDescending { it.ts })
        }
    }

    fun addSent(msg: SosMessage) {
        _sent.update { it + SentSos(msg, stage = 0, statusText = "Sending…") }
    }

    fun updateSentStatus(refSosId: String, stage: Int, text: String) {
        _sent.update { list ->
            list.map { s ->
                if (s.message.id == refSosId && stage > s.stage) {
                    s.copy(stage = stage, statusText = text)
                } else s
            }
        }
    }

    fun log(line: String) {
        _eventLog.update { (it + line).takeLast(200) }
    }

    fun setPeerCount(n: Int) {
        _peerCount.value = n
    }
}
