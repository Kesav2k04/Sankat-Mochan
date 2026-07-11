package com.sankatmochan.mesh.ui

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.draw.clip
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.DarkMode
import androidx.compose.material.icons.rounded.Hearing
import androidx.compose.material.icons.rounded.LightMode
import androidx.compose.material.icons.rounded.Sos
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import com.sankatmochan.mesh.mesh.MeshRole

/**
 * The role switch, as a modal. The phone is a victim's SOS console by default; this is the
 * one place to hand it to a responder instead. Relay is intentionally absent - this build
 * only offers the two jobs a person in the field actually chooses between.
 */
@Composable
fun RoleSettingsDialog(
    current: MeshRole,
    darkTheme: Boolean,
    onToggleTheme: () -> Unit,
    onSelect: (MeshRole) -> Unit,
    onDismiss: () -> Unit,
) {
    Dialog(onDismissRequest = onDismiss) {
        Surface(
            shape = TileShape,
            color = MaterialTheme.colorScheme.surfaceContainerHigh,
            border = null,
        ) {
            // Scrolls if the viewport is short (small phone, landscape, or a large system
            // font scale) so the appearance row is never clipped below the fold; capped to
            // most of the screen height so the dialog never runs edge to edge.
            Column(
                Modifier
                    .heightIn(max = 560.dp)
                    .verticalScroll(rememberScrollState())
                    .padding(20.dp)
            ) {
                SectionLabel("this phone's job")
                Spacer(Modifier.size(14.dp))
                RoleOption(
                    icon = Icons.Rounded.Sos,
                    tint = MaterialTheme.colorScheme.primary,
                    title = "User",
                    desc = "Send an SOS when you need help",
                    selected = current == MeshRole.VICTIM,
                ) { onSelect(MeshRole.VICTIM) }
                Spacer(Modifier.size(12.dp))
                RoleOption(
                    icon = Icons.Rounded.Hearing,
                    tint = MaterialTheme.colorScheme.secondary,
                    title = "Responder",
                    desc = "See incoming calls and accept them",
                    selected = current == MeshRole.RESPONDER,
                ) { onSelect(MeshRole.RESPONDER) }

                Spacer(Modifier.size(20.dp))
                SectionLabel("appearance")
                Spacer(Modifier.size(14.dp))
                ThemeToggleRow(darkTheme = darkTheme, onToggle = onToggleTheme)
            }
        }
    }
}

/** Light/dark switch. Dark is the control-room default; light makes the offline map read
 *  clearly in daylight against its light OSM tiles. */
@Composable
private fun ThemeToggleRow(darkTheme: Boolean, onToggle: () -> Unit) {
    val scheme = MaterialTheme.colorScheme
    Tile(
        modifier = Modifier
            .fillMaxWidth()
            .bounceClick { onToggle() },
        shape = TileShapeSmall,
        container = scheme.surfaceContainerHighest,
        stroke = scheme.outlineVariant,
    ) {
        Row(
            Modifier.padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            IconBadge(
                if (darkTheme) Icons.Rounded.DarkMode else Icons.Rounded.LightMode,
                tint = if (darkTheme) scheme.secondary else MaterialTheme.colorScheme.primary,
                size = 40.dp,
            )
            Column(Modifier.weight(1f)) {
                Text(
                    if (darkTheme) "Dark" else "Light",
                    style = MaterialTheme.typography.titleMedium,
                    color = scheme.onSurface,
                )
                Text(
                    "Switch the map and app to a light theme for daylight",
                    style = MaterialTheme.typography.bodySmall,
                    color = scheme.onSurfaceVariant,
                )
            }
            GlassSwitch(checked = !darkTheme, onChange = { onToggle() }, label = "Light theme")
        }
    }
}

@Composable
private fun RoleOption(
    icon: ImageVector,
    tint: Color,
    title: String,
    desc: String,
    selected: Boolean,
    onClick: () -> Unit,
) {
    val scheme = MaterialTheme.colorScheme
    val container by animateColorAsState(
        if (selected) tint.copy(alpha = 0.12f) else scheme.surfaceContainerHighest,
        tween(Motion.Fast), label = "roleBg"
    )
    val stroke by animateColorAsState(
        if (selected) tint.copy(alpha = 0.5f) else scheme.outlineVariant,
        tween(Motion.Fast), label = "roleStroke"
    )
    Tile(
        modifier = Modifier
            .fillMaxWidth()
            .bounceClick(onClick = onClick),
        shape = TileShapeSmall,
        container = container,
        stroke = stroke,
    ) {
        Row(
            Modifier.padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            IconBadge(icon, tint = tint, size = 40.dp)
            Column(Modifier.weight(1f)) {
                Text(
                    title,
                    style = MaterialTheme.typography.titleMedium,
                    color = scheme.onSurface
                )
                Text(
                    desc,
                    style = MaterialTheme.typography.bodySmall,
                    color = scheme.onSurfaceVariant
                )
            }
            if (selected) {
                Box(
                    Modifier
                        .size(24.dp)
                        .clip(CircleShape)
                        .background(tint),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        Icons.Rounded.Check,
                        contentDescription = "Selected",
                        tint = Color.White,
                        modifier = Modifier.size(16.dp)
                    )
                }
            }
        }
    }
}
