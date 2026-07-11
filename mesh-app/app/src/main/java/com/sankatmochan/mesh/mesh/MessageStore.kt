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
 * simple (no DB) - a phone reboot clears it, which is fine for the demo. The
 * seen-id set is what makes store-and-forward loop-free.
 */
class MessageStore {

    // Bounded, not a raw HashSet: dedup ids come straight off the untrusted mesh, so an
    // unbounded set is a memory-exhaustion DoS (see [BoundedIdSet]).
    private val seenIds = BoundedIdSet()

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
    fun markSeen(id: String): Boolean = seenIds.add(id)

    fun markAccepted(sosId: String) {
        _acceptedIds.update { it + sosId }
    }

    // These run on BLE binder threads; update{} is atomic (no lost-update race).
    fun addReceivedSos(msg: SosMessage) {
        _receivedSos.update { current ->
            // Most urgent first, then newest - a fresh CRITICAL must never sort
            // below a stale one the responder has already read past.
            // Capped so a flood of unique-id SOS packets (untrusted input, CLAUDE.md #8) can't
            // grow this list - and the O(n log n) re-sort it drives - without bound. The cap
            // keeps the highest-urgency, most-recent messages, which is exactly what a
            // responder must not lose; it sits far above any real incident's volume.
            (current + msg).distinctBy { it.id }
                .sortedWith(compareByDescending<SosMessage> { it.urgency }.thenByDescending { it.ts })
                .take(MAX_RECEIVED_SOS)
        }
    }

    fun addSent(msg: SosMessage) {
        _sent.update { it + SentSos(msg, stage = 0, statusText = "Sending…") }
    }

    /** Drop this device's originated-SOS list, returning the console to a clean slate. Called
     *  when the app is reopened after being left, so a previous session's SOS never greets the
     *  user on relaunch. Received-SOS and dedup bookkeeping are deliberately untouched: those
     *  belong to the mesh's correctness, not to one victim's screen. */
    fun clearSent() {
        _sent.value = emptyList()
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

    private companion object {
        /** Hard cap on the retained received-SOS list. Far above any real incident, small
         *  enough that a flood can never blow up memory or the per-message re-sort. */
        const val MAX_RECEIVED_SOS = 300
    }
}
