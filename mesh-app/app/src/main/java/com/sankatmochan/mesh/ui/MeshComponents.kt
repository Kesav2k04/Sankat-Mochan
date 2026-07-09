package com.sankatmochan.mesh.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/** Shared header: back button, screen title, and a live connected-peer badge. */
@Composable
fun MeshTopBar(title: String, peers: Int, onBack: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 8.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        IconButton(onClick = onBack) {
            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
        }
        Text(
            text = title,
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.weight(1f)
        )
        PeerBadge(peers)
    }
}

/**
 * Operator switch for the LoRa-only demo. When on, this phone stops connecting to
 * other phones, so the only route out is the Pi gateway's 433 MHz radio. Both
 * endpoint phones must have it on.
 */
@Composable
fun LoraOnlyBanner(enabled: Boolean, onChange: (Boolean) -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(if (enabled) Color(0xFF1B3A2A) else Color(0xFF2A2A2A))
            .padding(horizontal = 16.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = "LoRa-only mode",
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.Bold,
                color = Color.White
            )
            Text(
                text = if (enabled) "Ignoring nearby phones — messages must cross the radio bridge"
                else "Will also relay directly phone-to-phone over Bluetooth",
                style = MaterialTheme.typography.labelSmall,
                color = Color(0xFFBDBDBD)
            )
        }
        Switch(checked = enabled, onCheckedChange = onChange)
    }
}

@Composable
fun PeerBadge(peers: Int) {
    val connected = peers > 0
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier
                .size(10.dp)
                .clip(CircleShape)
                .background(if (connected) Color(0xFF2E7D32) else Color(0xFFB0651F))
        )
        Text(
            text = "  $peers peer${if (peers == 1) "" else "s"}",
            style = MaterialTheme.typography.labelLarge
        )
    }
}

/** Colour-coded urgency chip (1 low → 5 critical). */
@Composable
fun UrgencyChip(urgency: Int) {
    val (bg, label) = when (urgency) {
        5 -> Color(0xFFC62828) to "CRITICAL"
        4 -> Color(0xFFE64A19) to "HIGH"
        3 -> Color(0xFFF9A825) to "MEDIUM"
        2 -> Color(0xFF7CB342) to "LOW"
        else -> Color(0xFF9E9E9E) to "INFO"
    }
    Text(
        text = "$label · $urgency",
        color = Color.White,
        fontWeight = FontWeight.Bold,
        style = MaterialTheme.typography.labelMedium,
        modifier = Modifier
            .clip(RoundedCornerShape(6.dp))
            .background(bg)
            .padding(horizontal = 8.dp, vertical = 4.dp)
    )
}
