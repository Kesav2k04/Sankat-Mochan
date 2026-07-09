package com.sankatmochan.mesh.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.sankatmochan.mesh.MeshViewModel

@Composable
fun ResponderScreen(vm: MeshViewModel, peers: Int, onBack: () -> Unit) {
    val sosList by vm.receivedSos.collectAsState()
    val accepted = remember { mutableStateMapOf<String, Boolean>() }

    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(Modifier.fillMaxSize()) {
            MeshTopBar("Responder", peers, onBack)
            if (sosList.isEmpty()) {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(24.dp),
                    verticalArrangement = Arrangement.Center
                ) {
                    Text("No SOS yet.", style = MaterialTheme.typography.titleMedium)
                    Text(
                        "Waiting for calls over the mesh… ($peers peer${if (peers == 1) "" else "s"} connected)",
                        style = MaterialTheme.typography.bodyMedium
                    )
                }
            } else {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    items(sosList, key = { it.id }) { sos ->
                        SosCard(
                            urgency = sos.urgency,
                            category = sos.category,
                            gist = sos.gist,
                            location = sos.locationHint,
                            lat = sos.lat,
                            lng = sos.lng,
                            lang = sos.lang,
                            hops = sos.hops,
                            accepted = accepted[sos.id] == true,
                            onAccept = {
                                vm.accept(sos)
                                accepted[sos.id] = true
                            }
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun SosCard(
    urgency: Int,
    category: String,
    gist: String,
    location: String,
    lat: Double?,
    lng: Double?,
    lang: String,
    hops: Int,
    accepted: Boolean,
    onAccept: () -> Unit
) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                UrgencyChip(urgency)
                Spacer(Modifier.weight(1f))
                Text("hop $hops · $lang", style = MaterialTheme.typography.labelMedium)
            }
            Text(category.uppercase(), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            // gist is untrusted incoming text — rendered as plain text only (CLAUDE.md #9).
            Text(gist, style = MaterialTheme.typography.bodyLarge)
            if (location.isNotBlank()) {
                Text("📍 $location", style = MaterialTheme.typography.bodyMedium)
            }
            if (lat != null && lng != null) {
                Text(
                    "🛰 %.5f, %.5f".format(lat, lng),
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.SemiBold
                )
            }
            Spacer(Modifier.height(4.dp))
            Button(
                onClick = onAccept,
                enabled = !accepted,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(if (accepted) "✔ Accepted — en route" else "Accept & respond")
            }
        }
    }
}
