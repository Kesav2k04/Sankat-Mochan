package com.sankatmochan.mesh.ui

import android.text.format.DateUtils
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.sankatmochan.mesh.ui.theme.urgencyColors

/** Shared header: back button, screen title, and a live connected-peer badge. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MeshTopBar(title: String, peers: Int, onBack: () -> Unit) {
    TopAppBar(
        title = { Text(title, fontWeight = FontWeight.Bold) },
        navigationIcon = {
            IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Leave this role")
            }
        },
        actions = { PeerBadge(peers) },
        colors = TopAppBarDefaults.topAppBarColors(
            containerColor = MaterialTheme.colorScheme.surface,
            titleContentColor = MaterialTheme.colorScheme.onSurface,
        )
    )
}

/**
 * Operator switch for the LoRa-only demo. When on, this phone stops connecting to
 * other phones, so the only route out is the Pi gateway's 433 MHz radio. Both
 * endpoint phones must have it on — one phone left off will dial into the other.
 */
@Composable
fun LoraOnlyBanner(enabled: Boolean, onChange: (Boolean) -> Unit) {
    val scheme = MaterialTheme.colorScheme
    val container = if (enabled) scheme.primaryContainer else scheme.surfaceVariant
    val onContainer = if (enabled) scheme.onPrimaryContainer else scheme.onSurfaceVariant
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(container)
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = if (enabled) "LoRa-only mode · ON" else "LoRa-only mode · OFF",
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.Bold,
                color = onContainer
            )
            Text(
                text = if (enabled)
                    "Ignoring nearby phones — messages must cross the 433 MHz bridge"
                else
                    "Will also relay phone-to-phone over Bluetooth, skipping the radio",
                style = MaterialTheme.typography.labelSmall,
                color = onContainer
            )
        }
        Switch(
            checked = enabled,
            onCheckedChange = onChange,
            colors = SwitchDefaults.colors(
                checkedThumbColor = scheme.primary,
                checkedTrackColor = scheme.primary.copy(alpha = 0.35f),
            ),
            modifier = Modifier.semantics { contentDescription = "LoRa-only mode" }
        )
    }
}

@Composable
fun PeerBadge(peers: Int) {
    val connected = peers > 0
    val dot = if (connected) urgencyColors.low else urgencyColors.high
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .padding(end = 12.dp)
            .semantics {
                contentDescription =
                    if (connected) "$peers peers connected" else "No peers connected"
            }
    ) {
        Box(
            modifier = Modifier
                .size(10.dp)
                .clip(CircleShape)
                .background(dot)
        )
        Text(
            text = "  $peers",
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onSurface
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
        fontWeight = FontWeight.Bold,
        style = MaterialTheme.typography.labelMedium,
        modifier = Modifier
            .clip(RoundedCornerShape(6.dp))
            .background(palette.forLevel(urgency))
            .padding(horizontal = 10.dp, vertical = 5.dp)
    )
}

/**
 * A tappable pill. Material's own FilterChip is a fixed 32dp tall, which is hard to
 * hit with wet or shaking hands, so this one is sized for the field.
 */
@Composable
fun OptionChip(label: String, selected: Boolean, onClick: () -> Unit) {
    val scheme = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(10.dp)
    Text(
        text = label,
        style = MaterialTheme.typography.labelLarge,
        fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal,
        color = if (selected) scheme.onPrimary else scheme.onSurfaceVariant,
        modifier = Modifier
            .clip(shape)
            .background(if (selected) scheme.primary else Color.Transparent)
            .border(1.dp, if (selected) scheme.primary else scheme.outline, shape)
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 12.dp)
    )
}

/** Row of [OptionChip]s. `options` maps a wire value to the label the user reads. */
@Composable
fun ChipRow(
    options: List<Pair<String, String>>,
    selected: String,
    onSelect: (String) -> Unit,
) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        modifier = Modifier.horizontalScroll(rememberScrollState())
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
