package com.sankatmochan.mesh.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.BluetoothDisabled
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material.icons.rounded.Hearing
import androidx.compose.material.icons.rounded.Podcasts
import androidx.compose.material.icons.rounded.Sos
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sankatmochan.mesh.mesh.MeshRole
import com.sankatmochan.mesh.ui.theme.brandGradients
import com.sankatmochan.mesh.ui.theme.urgencyColors

/**
 * Home. A wordmark, one editorial headline over a sketched mesh, and a bento of the
 * three jobs this phone can take — the red hero first, because the person who needs
 * it is the one who can't afford to search.
 */
@Composable
fun RoleSelectionScreen(
    nodeId: String,
    bluetoothReady: Boolean,
    onPick: (MeshRole) -> Unit
) {
    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .safeDrawingPadding()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp)
        ) {
            Spacer(Modifier.height(20.dp))

            // Wordmark row.
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .entrance(0)
            ) {
                LogoMark(40.dp)
                Spacer(Modifier.size(12.dp))
                Column {
                    Text(
                        "OFF-NET",
                        style = MaterialTheme.typography.titleLarge,
                        letterSpacing = 3.sp,
                        color = MaterialTheme.colorScheme.onBackground
                    )
                    SectionLabel("off-grid sos mesh")
                }
                Spacer(Modifier.weight(1f))
                StandbyPill(bluetoothReady)
            }

            Spacer(Modifier.height(36.dp))

            // Headline over the hand-sketched mesh.
            Box(Modifier.fillMaxWidth().entrance(1)) {
                MeshDoodle(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(150.dp),
                    alpha = 0.35f
                )
                Text(
                    text = "Help travels,\neven when\nnetworks don't.",
                    style = MaterialTheme.typography.displaySmall,
                    color = MaterialTheme.colorScheme.onBackground,
                    modifier = Modifier.padding(top = 8.dp)
                )
            }

            Spacer(Modifier.height(32.dp))

            if (!bluetoothReady) {
                BluetoothWarning(Modifier.entrance(2))
                Spacer(Modifier.height(16.dp))
            }

            SectionLabel("choose this phone's job", Modifier.entrance(2))
            Spacer(Modifier.height(12.dp))

            // Hero: the victim tile.
            Tile(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(168.dp)
                    .entrance(3)
                    .softGlow(brandGradients.sosGlow, TileShape, elevation = 26.dp, alpha = 0.4f)
                    .bounceClick { onPick(MeshRole.VICTIM) },
                container = Color.Transparent,
                stroke = Color.Transparent,
            ) {
                Box(
                    Modifier
                        .fillMaxSize()
                        .background(brandGradients.sos)
                ) {
                    Column(Modifier.fillMaxSize().padding(20.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(
                                Modifier
                                    .size(44.dp)
                                    .clip(CircleShape)
                                    .background(Color.White),
                                contentAlignment = Alignment.Center
                            ) {
                                Icon(
                                    Icons.Rounded.Sos,
                                    contentDescription = null,
                                    tint = MaterialTheme.colorScheme.primary,
                                    modifier = Modifier.size(24.dp)
                                )
                            }
                            Spacer(Modifier.weight(1f))
                            Icon(
                                Icons.Rounded.ChevronRight,
                                contentDescription = null,
                                tint = Color.White.copy(alpha = 0.9f)
                            )
                        }
                        Spacer(Modifier.weight(1f))
                        Text(
                            "I need help",
                            style = MaterialTheme.typography.headlineMedium,
                            color = Color.White
                        )
                        Text(
                            "One tap sends an SOS across the mesh",
                            style = MaterialTheme.typography.bodyMedium,
                            color = Color.White.copy(alpha = 0.85f)
                        )
                    }
                }
            }

            Spacer(Modifier.height(12.dp))

            // The two quiet jobs, side by side.
            Row(
                Modifier.fillMaxWidth().entrance(4),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                QuietRoleTile(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Rounded.Hearing,
                    tint = MaterialTheme.colorScheme.secondary,
                    title = "Respond",
                    desc = "See incoming calls, accept them",
                ) { onPick(MeshRole.RESPONDER) }
                QuietRoleTile(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Rounded.Podcasts,
                    tint = urgencyColors.info,
                    title = "Relay",
                    desc = "Silently pass messages along",
                ) { onPick(MeshRole.RELAY) }
            }

            Spacer(Modifier.height(28.dp))
            Text(
                text = "NODE $nodeId".uppercase(),
                style = MaterialTheme.typography.labelSmall,
                fontFamily = FontFamily.Monospace,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f),
                modifier = Modifier
                    .align(Alignment.CenterHorizontally)
                    .entrance(5)
                    .padding(bottom = 24.dp)
            )
        }
    }
}

@Composable
private fun StandbyPill(bluetoothReady: Boolean) {
    val ok = bluetoothReady
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .clip(CircleShape)
            .background(MaterialTheme.colorScheme.surfaceContainerHigh)
            .padding(horizontal = 12.dp, vertical = 7.dp)
    ) {
        Box(
            Modifier
                .size(7.dp)
                .clip(CircleShape)
                .background(if (ok) urgencyColors.low else urgencyColors.medium)
        )
        Spacer(Modifier.size(7.dp))
        SectionLabel(if (ok) "ready" else "bt off")
    }
}

@Composable
private fun BluetoothWarning(modifier: Modifier = Modifier) {
    Tile(
        modifier = modifier.fillMaxWidth(),
        container = urgencyColors.medium.copy(alpha = 0.12f),
        stroke = urgencyColors.medium.copy(alpha = 0.35f),
    ) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            IconBadge(Icons.Rounded.BluetoothDisabled, tint = urgencyColors.medium)
            Spacer(Modifier.size(14.dp))
            Column {
                Text(
                    "Bluetooth is off",
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Text(
                    "The mesh cannot reach anything without it. It still works in aeroplane mode.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@Composable
private fun QuietRoleTile(
    modifier: Modifier,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    tint: Color,
    title: String,
    desc: String,
    onClick: () -> Unit,
) {
    Tile(
        modifier = modifier
            .aspectRatio(1.06f)
            .bounceClick(onClick = onClick),
        container = MaterialTheme.colorScheme.surfaceContainerHigh,
    ) {
        Column(Modifier.fillMaxSize().padding(16.dp)) {
            Row {
                IconBadge(icon, tint = tint)
                Spacer(Modifier.weight(1f))
                Icon(
                    Icons.Rounded.ChevronRight,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f),
                    modifier = Modifier.size(20.dp)
                )
            }
            Spacer(Modifier.weight(1f))
            Text(
                title,
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.onSurface
            )
            Spacer(Modifier.height(2.dp))
            Text(
                desc,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                lineHeight = 16.sp
            )
        }
    }
}
