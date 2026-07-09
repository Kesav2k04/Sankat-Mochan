package com.sankatmochan.mesh.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.sankatmochan.mesh.mesh.MeshRole

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
                .padding(24.dp),
            verticalArrangement = Arrangement.Center
        ) {
            Text(
                text = "Sankat-Mochan",
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary
            )
            Text(
                text = "Off-grid rescue mesh · node $nodeId",
                style = MaterialTheme.typography.bodyMedium
            )
            Spacer(Modifier.height(8.dp))
            if (!bluetoothReady) {
                Text(
                    text = "⚠ Turn on Bluetooth before choosing a role.",
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodyMedium
                )
            }
            Spacer(Modifier.height(24.dp))
            Text("Choose this device's role", fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(12.dp))

            RoleCard("🆘  Victim", "One-tap SOS + status", MeshRole.VICTIM, onPick)
            Spacer(Modifier.height(12.dp))
            RoleCard("🚑  Responder", "Receive & accept nearby SOS", MeshRole.RESPONDER, onPick)
            Spacer(Modifier.height(12.dp))
            RoleCard("📡  Relay", "Silently forward mesh traffic", MeshRole.RELAY, onPick)
        }
    }
}

@Composable
private fun RoleCard(title: String, subtitle: String, role: MeshRole, onPick: (MeshRole) -> Unit) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onPick(role) }
    ) {
        Column(Modifier.padding(20.dp)) {
            Text(title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Text(subtitle, style = MaterialTheme.typography.bodyMedium)
        }
    }
}
