package com.sankatmochan.mesh.ui

import android.text.format.DateUtils
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CellTower
import androidx.compose.material.icons.rounded.ChevronLeft
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.sankatmochan.mesh.ui.theme.urgencyColors

/**
 * Shared header: circular back chip, screen title over a quiet caption, live peer pill.
 * No bar fill — the page is one sheet.
 */
@Composable
fun MeshTopBar(title: String, caption: String, peers: Int, onBack: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            Modifier
                .size(42.dp)
                .clip(CircleShape)
                .background(MaterialTheme.colorScheme.surfaceContainerHigh)
                .border(1.dp, MaterialTheme.colorScheme.outlineVariant, CircleShape)
                .bounceClick(pressedScale = 0.9f, onClick = onBack)
                .semantics { contentDescription = "Leave this role" },
            contentAlignment = Alignment.Center
        ) {
            Icon(
                Icons.Rounded.ChevronLeft,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurface
            )
        }
        Spacer(Modifier.size(14.dp))
        Column(Modifier.weight(1f)) {
            Text(
                title,
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.onBackground,
                maxLines = 1
            )
            Text(
                caption.uppercase(),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
        Spacer(Modifier.size(10.dp))
        PeerBadge(peers)
    }
}

/**
 * Operator switch for the LoRa-only demo, as a bridge tile. When on, this phone stops
 * connecting to other phones, so the only route out is the Pi gateway's 433 MHz radio.
 * Both endpoint phones must have it on — one left off will dial into the other.
 */
@Composable
fun LoraOnlyBanner(enabled: Boolean, onChange: (Boolean) -> Unit) {
    val scheme = MaterialTheme.colorScheme
    val container by animateColorAsState(
        if (enabled) scheme.primaryContainer else scheme.surfaceContainer,
        tween(Motion.Fast),
        label = "loraBg"
    )
    val stroke by animateColorAsState(
        if (enabled) scheme.primary.copy(alpha = 0.5f) else scheme.outlineVariant,
        tween(Motion.Fast),
        label = "loraStroke"
    )
    Tile(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 6.dp),
        shape = TileShapeSmall,
        container = container,
        stroke = stroke,
    ) {
        Row(
            Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconBadge(
                Icons.Rounded.CellTower,
                tint = if (enabled) scheme.primary else scheme.onSurfaceVariant,
                size = 34.dp
            )
            Spacer(Modifier.size(12.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    "LoRa bridge",
                    style = MaterialTheme.typography.titleMedium,
                    color = if (enabled) scheme.onPrimaryContainer else scheme.onSurface
                )
                Text(
                    text = if (enabled)
                        "Phones ignored — everything crosses the 433 MHz radio"
                    else
                        "Off — relaying phone-to-phone over Bluetooth",
                    style = MaterialTheme.typography.bodySmall,
                    color = scheme.onSurfaceVariant
                )
            }
            Spacer(Modifier.size(12.dp))
            GlassSwitch(checked = enabled, onChange = onChange, label = "LoRa-only mode")
        }
    }
}

/** Live peer count: pulsing state dot + count + MESH caption, as a pill. */
@Composable
fun PeerBadge(peers: Int) {
    val connected = peers > 0
    val dot = if (connected) urgencyColors.low else urgencyColors.critical
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .clip(CircleShape)
            .background(MaterialTheme.colorScheme.surfaceContainerHigh)
            .border(1.dp, MaterialTheme.colorScheme.outlineVariant, CircleShape)
            .padding(horizontal = 14.dp, vertical = 8.dp)
            .semantics {
                contentDescription =
                    if (connected) "$peers peers connected" else "No peers connected"
            }
    ) {
        Box(
            modifier = Modifier
                .size(8.dp)
                .clip(CircleShape)
                .background(dot)
        )
        Spacer(Modifier.size(8.dp))
        Text(
            text = "$peers",
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onSurface,
            maxLines = 1
        )
        Spacer(Modifier.size(6.dp))
        Text(
            "MESH",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            maxLines = 1,
            softWrap = false
        )
    }
}

/** Colour-coded urgency chip (1 low → 5 critical). */
@Composable
fun UrgencyChip(urgency: Int) {
    val palette = urgencyColors
    Text(
        text = palette.labelFor(urgency),
        color = palette.onLevel(urgency),
        style = MaterialTheme.typography.labelMedium,
        modifier = Modifier
            .clip(RoundedCornerShape(8.dp))
            .background(palette.forLevel(urgency))
            .padding(horizontal = 10.dp, vertical = 5.dp)
    )
}

/**
 * A tappable pill sized for the field — Material's own FilterChip is a fixed 32dp tall,
 * hard to hit with wet or shaking hands. Selected fills red; the press bounces.
 */
@Composable
fun OptionChip(label: String, selected: Boolean, onClick: () -> Unit) {
    val scheme = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(12.dp)
    val bg by animateColorAsState(
        if (selected) scheme.primary else scheme.surfaceContainerHigh,
        tween(Motion.Fast),
        label = "chipBg"
    )
    val fg by animateColorAsState(
        if (selected) scheme.onPrimary else scheme.onSurfaceVariant,
        tween(Motion.Fast),
        label = "chipFg"
    )
    Text(
        text = label,
        style = MaterialTheme.typography.labelLarge,
        fontWeight = if (selected) FontWeight.Bold else FontWeight.Medium,
        color = fg,
        modifier = Modifier
            .clip(shape)
            .background(bg)
            .border(1.dp, if (selected) Color.Transparent else scheme.outline, shape)
            .bounceClick(pressedScale = 0.93f, onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 12.dp)
    )
}

/**
 * Wrapping row of [OptionChip]s. `options` maps a wire value to the label the user reads.
 * FlowRow wraps rather than scrolling sideways, so no option hides off the right edge.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ChipRow(
    options: List<Pair<String, String>>,
    selected: String,
    onSelect: (String) -> Unit,
) {
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        options.forEach { (value, label) ->
            OptionChip(label = label, selected = value == selected) { onSelect(value) }
        }
    }
}

/** "2 minutes ago", from an epoch-millis timestamp. */
fun relativeTime(ts: Long): String {
    if (ts <= 0L) return "just now"
    return DateUtils.getRelativeTimeSpanString(
        ts, System.currentTimeMillis(), DateUtils.MINUTE_IN_MILLIS
    ).toString()
}

/** How an envelope reached us. hops == 0 means it never left the origin phone. */
fun routeLabel(hops: Int): String = when (hops) {
    0 -> "direct"
    1 -> "1 hop · via the bridge"
    else -> "$hops hops · via the bridge"
}
