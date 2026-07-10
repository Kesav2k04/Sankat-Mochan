package com.sankatmochan.mesh.ui

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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Podcasts
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sankatmochan.mesh.MeshViewModel
import com.sankatmochan.mesh.ui.theme.urgencyColors

/**
 * The relay has no decisions to make, so this screen answers one question at a glance:
 * is this device doing its job? Two counters and a live wire.
 */
@Composable
fun RelayScreen(vm: MeshViewModel, peers: Int, onBack: () -> Unit) {
    val log by vm.eventLog.collectAsState()
    val received by vm.receivedSos.collectAsState()

    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(Modifier.fillMaxSize()) {
            MeshTopBar("Relay", "store & forward", peers, onBack)

            Column(
                Modifier
                    .fillMaxSize()
                    .padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth().entrance(0),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    StatTile("peers", peers.toString(), Modifier.weight(1f))
                    StatTile("carried", received.size.toString(), Modifier.weight(1f))
                }

                Tile(Modifier.fillMaxWidth().entrance(1), shape = TileShapeSmall) {
                    Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        IconBadge(
                            Icons.Rounded.Podcasts,
                            tint = urgencyColors.low,
                            size = 36.dp
                        )
                        Spacer(Modifier.size(12.dp))
                        Text(
                            "Silently stores and forwards every SOS it hears. " +
                                "Leave it running somewhere central.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }

                SectionLabel("live wire", Modifier.padding(start = 6.dp, top = 4.dp).entrance(2))
                Tile(
                    Modifier
                        .fillMaxSize()
                        .padding(bottom = 16.dp)
                        .entrance(2),
                    container = MaterialTheme.colorScheme.surfaceContainerLowest,
                ) {
                    if (log.isEmpty()) {
                        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                            Text(
                                "Nothing has passed through yet.",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    } else {
                        val lines = log.asReversed()   // newest first
                        LazyColumn(Modifier.fillMaxSize().padding(14.dp)) {
                            items(lines) { line ->
                                Text(
                                    text = line,
                                    fontFamily = FontFamily.Monospace,
                                    fontSize = 12.sp,
                                    lineHeight = 18.sp,
                                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.8f),
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(vertical = 2.dp)
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun StatTile(label: String, value: String, modifier: Modifier = Modifier) {
    Tile(modifier = modifier) {
        Column(Modifier.padding(18.dp)) {
            Text(
                value,
                style = MaterialTheme.typography.headlineLarge,
                color = MaterialTheme.colorScheme.onSurface
            )
            Spacer(Modifier.height(4.dp))
            SectionLabel(label)
        }
    }
}
