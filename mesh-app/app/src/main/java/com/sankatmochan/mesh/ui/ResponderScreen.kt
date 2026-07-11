package com.sankatmochan.mesh.ui

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Hearing
import androidx.compose.material.icons.rounded.NearMe
import androidx.compose.material.icons.rounded.Place
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sankatmochan.mesh.MeshViewModel
import com.sankatmochan.mesh.mesh.VoiceClip
import com.sankatmochan.mesh.model.SosMessage
import com.sankatmochan.mesh.ui.theme.urgencyColors

@Composable
fun ResponderScreen(vm: MeshViewModel, peers: Int, onOpenSettings: () -> Unit) {
    val sosList by vm.receivedSos.collectAsState()
    val accepted by vm.acceptedIds.collectAsState()
    val voice by vm.voiceClips.collectAsState()

    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(Modifier.fillMaxSize()) {
            MeshTopBar("Incoming", "live SOS queue", peers, onSettings = onOpenSettings)

            if (sosList.isEmpty() && voice.isEmpty()) {
                EmptyQueue(peers)
            } else {
                val waiting = sosList.count { it.id !in accepted }
                // Correlate voice with text by originating node. A clip id is
                // "<origin>-v<seq>" and an SOS id is "<origin>-<seq>", so a shared `origin`
                // means the same phone sent both — that is what lets a recording ride inside
                // the SOS card it belongs to instead of sitting in a disconnected list where a
                // responder can't tell which text it matches. Each origin's clips attach to its
                // top-ranked SOS (sosList is already urgency- then recency-sorted).
                val clipsByOrigin = voice.groupBy { it.origin }
                val hostSosIdByOrigin = sosList
                    .groupBy { it.origin }
                    .mapValues { (_, group) -> group.first().id }
                // Clips whose sender has no SOS on this screen yet: show them on their own so a
                // recording arriving before its SOS is never lost.
                val orphanClips = voice.filter { it.origin !in hostSosIdByOrigin }
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    item(key = "stats") {
                        StatStrip(
                            waiting = waiting,
                            answered = sosList.size - waiting,
                            voices = voice.size
                        )
                    }
                    if (sosList.any { it.hasLocation }) {
                        item(key = "map") {
                            OfflineMapCard(
                                victims = sosList,
                                meLat = vm.lat,
                                meLng = vm.lng
                            )
                        }
                    }
                    // Unmatched voice first: a recording with no SOS yet is the most
                    // time-sensitive, still-arriving thing on this screen.
                    items(orphanClips, key = { it.clipId }) { clip ->
                        VoiceClipCard(clip)
                    }
                    items(sosList, key = { it.id }) { sos ->
                        val attached =
                            if (hostSosIdByOrigin[sos.origin] == sos.id)
                                clipsByOrigin[sos.origin].orEmpty()
                            else emptyList()
                        SosCard(
                            sos = sos,
                            accepted = sos.id in accepted,
                            route = Geo.describeRoute(vm.lat, vm.lng, sos.lat, sos.lng),
                            voiceClips = attached,
                            onAccept = { vm.accept(sos) }
                        )
                    }
                    item { Spacer(Modifier.height(12.dp)) }
                }
            }
        }
    }
}

/** Three mini-tiles: what's waiting, what's handled, what's on the air. */
@Composable
private fun StatStrip(waiting: Int, answered: Int, voices: Int) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        MiniStat("waiting", waiting.toString(), if (waiting > 0) urgencyColors.critical else urgencyColors.low, Modifier.weight(1f))
        MiniStat("answered", answered.toString(), urgencyColors.low, Modifier.weight(1f))
        MiniStat("voice", voices.toString(), MaterialTheme.colorScheme.secondary, Modifier.weight(1f))
    }
}

@Composable
private fun MiniStat(label: String, value: String, tint: Color, modifier: Modifier = Modifier) {
    Tile(modifier = modifier, shape = TileShapeSmall) {
        Column(Modifier.padding(horizontal = 14.dp, vertical = 12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier
                        .size(7.dp)
                        .clip(CircleShape)
                        .background(tint)
                )
                Spacer(Modifier.size(6.dp))
                SectionLabel(label)
            }
            Spacer(Modifier.height(4.dp))
            Text(
                value,
                style = MaterialTheme.typography.headlineSmall,
                color = MaterialTheme.colorScheme.onSurface
            )
        }
    }
}

@Composable
private fun EmptyQueue(peers: Int) {
    val infinite = rememberInfiniteTransition(label = "listen")
    val pulse by infinite.animateFloat(
        initialValue = 0.22f, targetValue = 0.06f,
        animationSpec = infiniteRepeatable(tween(1500), RepeatMode.Reverse),
        label = "listenPulse"
    )
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Box(contentAlignment = Alignment.Center) {
            Box(
                Modifier
                    .size(130.dp)
                    .clip(CircleShape)
                    .background(MaterialTheme.colorScheme.secondary.copy(alpha = pulse))
            )
            IconBadge(
                Icons.Rounded.Hearing,
                tint = MaterialTheme.colorScheme.secondary,
                size = 84.dp
            )
        }
        Spacer(Modifier.height(22.dp))
        Text(
            "Scanning",
            style = MaterialTheme.typography.headlineSmall,
            color = MaterialTheme.colorScheme.onBackground
        )
        Spacer(Modifier.height(8.dp))
        Text(
            text = if (peers > 0)
                "Connected to $peers device${if (peers == 1) "" else "s"}. Any SOS that reaches the mesh appears here."
            else
                "Nothing connected yet. Waiting for the gateway or another phone to come into range.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center
        )
    }
}

@Composable
private fun SosCard(
    sos: SosMessage,
    accepted: Boolean,
    route: String?,
    onAccept: () -> Unit,
    voiceClips: List<VoiceClip> = emptyList(),
) {
    val palette = urgencyColors
    val accent = palette.forLevel(sos.urgency)
    Tile(
        Modifier.fillMaxWidth(),
        stroke = if (accepted) palette.low.copy(alpha = 0.4f) else accent.copy(alpha = 0.3f)
    ) {
        Column(
            Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                UrgencyChip(sos.urgency)
                Spacer(Modifier.weight(1f))
                Text(
                    relativeTime(sos.ts),
                    style = MaterialTheme.typography.labelMedium,
                    letterSpacing = 0.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            Text(
                sos.category.ifBlank { "unspecified" }.uppercase(),
                style = MaterialTheme.typography.headlineSmall,
                color = MaterialTheme.colorScheme.onSurface
            )

            // gist is untrusted incoming text - rendered as plain text only (CLAUDE.md #9).
            if (sos.gist.isNotBlank()) {
                Text(
                    sos.gist,
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurface
                )
            }

            if (sos.locationHint.isNotBlank()) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        Icons.Rounded.Place,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(Modifier.size(5.dp))
                    Text(
                        sos.locationHint,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                }
            }

            if (sos.hasLocation) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (route != null) {
                        Icon(
                            Icons.Rounded.NearMe,
                            contentDescription = null,
                            modifier = Modifier.size(16.dp),
                            tint = accent
                        )
                        Spacer(Modifier.size(5.dp))
                        Text(
                            "$route from you",
                            style = MaterialTheme.typography.titleSmall,
                            color = accent
                        )
                        Spacer(Modifier.weight(1f))
                    }
                    Text(
                        "%.5f, %.5f".format(sos.lat, sos.lng),
                        style = MaterialTheme.typography.labelSmall,
                        letterSpacing = 0.sp,
                        fontFamily = FontFamily.Monospace,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            Text(
                "${routeLabel(sos.hops)} · ${sos.lang} · from ${sos.origin}",
                style = MaterialTheme.typography.labelSmall,
                letterSpacing = 0.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.8f)
            )

            // Voice recorded and sent WITH this SOS, shown inside its own card so the
            // recording and the text it belongs to are never split apart (matched by origin).
            if (voiceClips.isNotEmpty()) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    SectionLabel(if (voiceClips.size == 1) "attached voice" else "attached voice (${voiceClips.size})")
                    voiceClips.forEach { clip ->
                        Box(
                            Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(14.dp))
                                .background(MaterialTheme.colorScheme.surfaceContainerHighest.copy(alpha = 0.5f))
                        ) {
                            VoiceClipContent(
                                clip = clip,
                                modifier = Modifier.padding(12.dp),
                                hideOrigin = true,
                            )
                        }
                    }
                }
            }

            Spacer(Modifier.height(2.dp))
            if (accepted) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(14.dp))
                        .background(palette.low)
                        .padding(vertical = 15.dp),
                    horizontalArrangement = Arrangement.Center,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        Icons.Rounded.Check,
                        contentDescription = null,
                        tint = Color.White,
                        modifier = Modifier.size(18.dp)
                    )
                    Spacer(Modifier.size(8.dp))
                    Text(
                        "Accepted - en route",
                        color = Color.White,
                        style = MaterialTheme.typography.titleSmall
                    )
                }
            } else {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(54.dp)
                        .clip(RoundedCornerShape(14.dp))
                        .background(accent)
                        .bounceClick(onClick = onAccept),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        "Accept & respond",
                        color = palette.onLevel(sos.urgency),
                        style = MaterialTheme.typography.titleSmall
                    )
                }
            }
        }
    }
}
