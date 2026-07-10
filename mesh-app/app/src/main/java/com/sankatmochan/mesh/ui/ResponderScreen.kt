package com.sankatmochan.mesh.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Place
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.sankatmochan.mesh.MeshViewModel
import com.sankatmochan.mesh.model.SosMessage
import com.sankatmochan.mesh.ui.theme.urgencyColors

@Composable
fun ResponderScreen(vm: MeshViewModel, peers: Int, onBack: () -> Unit) {
    val sosList by vm.receivedSos.collectAsState()
    // Lives in the store, so it survives rotation and leaving/re-entering the screen.
    val accepted by vm.acceptedIds.collectAsState()

    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(Modifier.fillMaxSize()) {
            MeshTopBar("Incoming calls", peers, onBack)

            if (sosList.isEmpty()) {
                EmptyQueue(peers)
            } else {
                val waiting = sosList.count { it.id !in accepted }
                QueueHeader(total = sosList.size, waiting = waiting)
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    items(sosList, key = { it.id }) { sos ->
                        SosCard(
                            sos = sos,
                            accepted = sos.id in accepted,
                            onAccept = { vm.accept(sos) }
                        )
                    }
                    item { Spacer(Modifier.height(12.dp)) }
                }
            }
        }
    }
}

@Composable
private fun QueueHeader(total: Int, waiting: Int) {
    Text(
        text = if (waiting == 0) "All $total answered" else "$waiting waiting · $total total",
        style = MaterialTheme.typography.labelLarge,
        fontWeight = FontWeight.Bold,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp)
    )
}

@Composable
private fun EmptyQueue(peers: Int) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text("Listening", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(8.dp))
        Text(
            text = if (peers > 0)
                "Connected to $peers device${if (peers == 1) "" else "s"}. Any SOS that reaches the mesh will appear here."
            else
                "Nothing connected yet. Waiting for the gateway or another phone to come into range.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

@Composable
private fun SosCard(sos: SosMessage, accepted: Boolean, onAccept: () -> Unit) {
    val palette = urgencyColors
    Card(Modifier.fillMaxWidth()) {
        // IntrinsicSize.Min bounds the Row's height to its tallest child, which is what
        // lets the accent bar's fillMaxHeight() resolve inside an unbounded LazyColumn item.
        Row(
            Modifier
                .fillMaxWidth()
                .height(IntrinsicSize.Min)
        ) {
            // Urgency reads as a colour before it reads as a word.
            Box(
                Modifier
                    .width(6.dp)
                    .fillMaxHeight()
                    .background(palette.forLevel(sos.urgency))
            )
            Column(
                Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    UrgencyChip(sos.urgency)
                    Spacer(Modifier.weight(1f))
                    Text(
                        relativeTime(sos.ts),
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                Text(
                    sos.category.ifBlank { "unspecified" }.uppercase(),
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.titleMedium
                )

                // gist is untrusted incoming text — rendered as plain text only (CLAUDE.md #9).
                if (sos.gist.isNotBlank()) {
                    Text(sos.gist, style = MaterialTheme.typography.bodyLarge)
                }

                if (sos.locationHint.isNotBlank()) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            Icons.Filled.Place,
                            contentDescription = null,
                            modifier = Modifier.size(16.dp),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Spacer(Modifier.size(4.dp))
                        Text(sos.locationHint, style = MaterialTheme.typography.bodyMedium)
                    }
                }

                if (sos.hasLocation) {
                    Text(
                        "%.5f, %.5f".format(sos.lat, sos.lng),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.SemiBold
                    )
                }

                Text(
                    "${routeLabel(sos.hops)} · ${sos.lang} · from ${sos.origin}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )

                Spacer(Modifier.height(4.dp))
                if (accepted) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(8.dp))
                            .background(palette.low)
                            .padding(vertical = 14.dp),
                        horizontalArrangement = Arrangement.Center,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            Icons.Filled.Check,
                            contentDescription = null,
                            tint = Color.White,
                            modifier = Modifier.size(18.dp)
                        )
                        Spacer(Modifier.size(8.dp))
                        Text("Accepted — en route", color = Color.White, fontWeight = FontWeight.Bold)
                    }
                } else {
                    Button(
                        onClick = onAccept,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(52.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = palette.forLevel(sos.urgency),
                            contentColor = palette.onLevel(sos.urgency)
                        )
                    ) {
                        Text("Accept & respond", fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}
