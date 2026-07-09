package com.sankatmochan.mesh.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.sankatmochan.mesh.MeshViewModel

@Composable
fun VictimScreen(vm: MeshViewModel, peers: Int, onBack: () -> Unit) {
    // Prefilled with a realistic Tamil SOS so the demo needs one tap.
    var gist by remember { mutableStateOf("Veedu moodhi irukku, thanni varudhu — kaappaathunga") }
    var category by remember { mutableStateOf("trapped") }
    var location by remember { mutableStateOf("Sector 4, near temple") }
    var lang by remember { mutableStateOf("ta") }
    var urgency by remember { mutableIntStateOf(5) }

    val sent by vm.sent.collectAsState()
    val latest = sent.lastOrNull()

    // Try for a GPS fix as soon as the victim screen opens (optional — SOS works without it).
    LaunchedEffect(Unit) { vm.refreshLocation() }

    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(Modifier.fillMaxSize()) {
            MeshTopBar("Victim", peers, onBack)
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(16.dp)
            ) {
                OutlinedTextField(
                    value = gist,
                    onValueChange = { gist = it },
                    label = { Text("What's happening?") },
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(Modifier.height(8.dp))
                Row {
                    OutlinedTextField(
                        value = category,
                        onValueChange = { category = it },
                        label = { Text("Category") },
                        modifier = Modifier.weight(1f)
                    )
                    Spacer(Modifier.width(8.dp))
                    OutlinedTextField(
                        value = lang,
                        onValueChange = { lang = it },
                        label = { Text("Lang") },
                        modifier = Modifier.weight(0.5f)
                    )
                }
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = location,
                    onValueChange = { location = it },
                    label = { Text("Location hint") },
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(Modifier.height(8.dp))
                Text("Urgency: $urgency", fontWeight = FontWeight.SemiBold)
                Slider(
                    value = urgency.toFloat(),
                    onValueChange = { urgency = it.toInt() },
                    valueRange = 1f..5f,
                    steps = 3
                )
                Spacer(Modifier.height(12.dp))
                LocationCard(vm)

                Spacer(Modifier.height(16.dp))
                Button(
                    onClick = { vm.sendSos(category, urgency, gist, lang, location) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(72.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFC62828))
                ) {
                    Text("🆘  SEND SOS", style = MaterialTheme.typography.headlineSmall, color = Color.White)
                }

                if (peers == 0) {
                    Spacer(Modifier.height(8.dp))
                    Text(
                        "No device connected yet — your SOS will be delivered automatically as soon as one is in range.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error
                    )
                }

                Spacer(Modifier.height(24.dp))
                if (latest != null) {
                    StatusLadder(stage = latest.stage, statusText = latest.statusText)
                }
            }
        }
    }
}

@Composable
private fun LocationCard(vm: MeshViewModel) {
    Card(Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(Modifier.weight(1f)) {
                Text("📍 GPS location", fontWeight = FontWeight.SemiBold)
                val la = vm.lat
                val lo = vm.lng
                if (la != null && lo != null) {
                    Text("%.5f, %.5f".format(la, lo), style = MaterialTheme.typography.bodyLarge)
                }
                Text(vm.locationStatus, style = MaterialTheme.typography.bodySmall, color = Color.Gray)
            }
            TextButton(onClick = { vm.refreshLocation() }) { Text("Refresh") }
        }
    }
}

@Composable
private fun StatusLadder(stage: Int, statusText: String) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Status", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Step("Sending…", stage >= 0)
            Step("Message reached the control room", stage >= 1)
            Step("Help is on the way", stage >= 2)
            Spacer(Modifier.height(4.dp))
            Text(
                text = "Current: $statusText",
                color = MaterialTheme.colorScheme.primary,
                fontWeight = FontWeight.SemiBold
            )
        }
    }
}

@Composable
private fun Step(label: String, done: Boolean) {
    Row {
        Text(if (done) "●  " else "○  ", color = if (done) MaterialTheme.colorScheme.primary else Color.Gray)
        Text(label, color = if (done) MaterialTheme.colorScheme.onSurface else Color.Gray)
    }
}
