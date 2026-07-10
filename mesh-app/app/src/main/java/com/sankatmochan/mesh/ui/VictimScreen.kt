package com.sankatmochan.mesh.ui

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import android.util.Log
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Place
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sankatmochan.mesh.MeshViewModel
import com.sankatmochan.mesh.ui.theme.urgencyColors
import kotlinx.coroutines.delay

/** Kept in step with VoiceRecorder.MAX_MILLIS. */
private const val MAX_VOICE_SECONDS = 5

private val CATEGORIES = listOf(
    "trapped" to "Trapped",
    "medical" to "Medical",
    "flood" to "Flood",
    "fire" to "Fire",
    "supplies" to "Food / Water",
)

// Native script — the person choosing is choosing their own language.
private val LANGUAGES = listOf(
    "ta" to "தமிழ்",
    "hi" to "हिंदी",
    "en" to "English",
)

private val URGENCIES = listOf(
    "5" to "Critical",
    "4" to "High",
    "3" to "Medium",
    "2" to "Low",
    "1" to "Info",
)

/**
 * One tap must send an SOS. Everything else sits below the button and is optional —
 * a person in rising water does not fill in a form first, and the old screen made
 * them type a category, a landmark, and the literal language code "ta".
 */
@Composable
fun VictimScreen(vm: MeshViewModel, peers: Int, onBack: () -> Unit) {
    var gist by remember { mutableStateOf("") }
    var category by remember { mutableStateOf("trapped") }
    var location by remember { mutableStateOf("") }
    var lang by remember { mutableStateOf("ta") }
    var urgency by remember { mutableIntStateOf(5) }
    var detailsOpen by remember { mutableStateOf(false) }
    var justSent by remember { mutableStateOf(false) }

    val sent by vm.sent.collectAsState()
    val latest = sent.lastOrNull()

    // The GNSS receiver was already started when this role was picked, so by the time
    // anyone reaches this screen a fix is on its way. Nothing to kick off here.

    // Acknowledgement, not a send lock: the button stays live, so a second tap always
    // gets through. This only stops it reading "SEND" while the person is still
    // looking at the confirmation from the last one.
    LaunchedEffect(sent.size) {
        if (sent.isNotEmpty()) {
            justSent = true
            delay(2500)
            justSent = false
        }
    }

    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(Modifier.fillMaxSize()) {
            MeshTopBar("Send for help", peers, onBack)
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(16.dp)
            ) {
                // The status of an SOS already in flight outranks everything else,
                // so it goes above the button rather than below the fold.
                if (latest != null) {
                    StatusLadder(stage = latest.stage, statusText = latest.statusText)
                    if (sent.size > 1) {
                        Spacer(Modifier.height(6.dp))
                        Text(
                            "${sent.size} SOS sent from this phone",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    Spacer(Modifier.height(20.dp))
                }

                SosButton(
                    justSent = justSent,
                    repeat = sent.isNotEmpty(),
                    onSend = { vm.sendSos(category, urgency, gist, lang, location) }
                )

                Spacer(Modifier.height(12.dp))
                VoiceButton(vm)

                Spacer(Modifier.height(10.dp))
                ReachabilityNote(peers)
                Spacer(Modifier.height(6.dp))
                GpsNote(vm)

                Spacer(Modifier.height(20.dp))
                Text(
                    text = if (detailsOpen) "Hide details" else "Add details (optional)",
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier
                        .clip(RoundedCornerShape(8.dp))
                        .clickable { detailsOpen = !detailsOpen }
                        .padding(vertical = 10.dp, horizontal = 4.dp)
                )

                if (detailsOpen) {
                    Spacer(Modifier.height(8.dp))
                    Field("What is happening?") {
                        ChipRow(CATEGORIES, category) { category = it }
                    }
                    Field("How urgent?") {
                        ChipRow(URGENCIES, urgency.toString()) { urgency = it.toInt() }
                    }
                    Field("Language") {
                        ChipRow(LANGUAGES, lang) { lang = it }
                    }
                    Field("Anything else?") {
                        OutlinedTextField(
                            value = gist,
                            onValueChange = { gist = it },
                            placeholder = { Text("e.g. two children with me") },
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                    Field("Landmark near you") {
                        OutlinedTextField(
                            value = location,
                            onValueChange = { location = it },
                            placeholder = { Text("e.g. Sector 4, near the temple") },
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                    LocationCard(vm)
                    Spacer(Modifier.height(24.dp))
                }
            }
        }
    }
}

@Composable
private fun SosButton(justSent: Boolean, repeat: Boolean, onSend: () -> Unit) {
    val palette = urgencyColors
    val bg = if (justSent) palette.low else palette.critical
    val label = when {
        justSent -> "SENT"
        repeat -> "SEND AGAIN"
        else -> "SEND SOS"
    }
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(200.dp)
            .clip(RoundedCornerShape(20.dp))
            .background(bg)
            .clickable(onClick = onSend)
            .semantics { contentDescription = "Send an emergency SOS" },
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            if (justSent) {
                Icon(
                    Icons.Filled.Check,
                    contentDescription = null,
                    tint = Color.White,
                    modifier = Modifier.size(56.dp)
                )
            } else {
                Text("🆘", fontSize = 52.sp)
            }
            Spacer(Modifier.height(8.dp))
            Text(
                text = label,
                color = Color.White,
                fontSize = 34.sp,
                fontWeight = FontWeight.Black,
                textAlign = TextAlign.Center
            )
        }
    }
}

/** Says what will actually happen to the message, which depends on a peer being up. */
@Composable
private fun ReachabilityNote(peers: Int) {
    val connected = peers > 0
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            Modifier
                .size(8.dp)
                .clip(CircleShape)
                .background(if (connected) urgencyColors.low else urgencyColors.high)
        )
        Spacer(Modifier.size(8.dp))
        Text(
            text = if (connected)
                "Connected — your SOS goes out immediately"
            else
                "Nothing in range yet — your SOS is held and sent the moment a device comes into range",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

/**
 * Hold to speak, release to send.
 *
 * The 5-second cap is not a UI nicety. A 5-second Opus clip is ~3.7 kB, which is 22 LoRa
 * frames and about 7 seconds of airtime at SF7 — during which nobody else's SOS can get
 * through. Ten seconds would double that. The countdown shows the budget being spent.
 */
@Composable
private fun VoiceButton(vm: MeshViewModel) {
    val recording = vm.isRecording
    var remaining by remember { mutableIntStateOf(MAX_VOICE_SECONDS) }

    // Hard stop at the cap even if the finger never lifts.
    LaunchedEffect(recording) {
        if (!recording) { remaining = MAX_VOICE_SECONDS; return@LaunchedEffect }
        remaining = MAX_VOICE_SECONDS
        while (remaining > 0) {
            delay(1000)
            remaining--
        }
        vm.stopRecordingAndSend()
    }

    Column {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(64.dp)
                .clip(RoundedCornerShape(14.dp))
                .background(if (recording) urgencyColors.critical else MaterialTheme.colorScheme.surfaceVariant)
                .pointerInput(Unit) {
                    detectTapGestures(
                        onPress = {
                            vm.startRecording()
                            // Suspends until the finger lifts or the gesture is cancelled.
                            val completed = tryAwaitRelease()
                            if (completed) vm.stopRecordingAndSend() else vm.cancelRecording()
                        }
                    )
                }
                .semantics { contentDescription = "Hold to record a voice message" },
            contentAlignment = Alignment.Center
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    Icons.Filled.Mic,
                    contentDescription = null,
                    tint = if (recording) Color.White else MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.size(10.dp))
                Text(
                    text = if (recording) "Recording — release to send ($remaining s)"
                    else "Hold to record a voice message",
                    fontWeight = FontWeight.Bold,
                    color = if (recording) Color.White else MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
        if (vm.voiceStatus.isNotBlank() && !recording) {
            Spacer(Modifier.height(4.dp))
            Text(
                vm.voiceStatus,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

/**
 * Whether coordinates will ride along with the SOS. Shown next to the button, because
 * a fix that only appears once you open "Add details" may as well not exist.
 */
@Composable
private fun GpsNote(vm: MeshViewModel) {
    val context = LocalContext.current
    val hasFix = vm.lat != null && vm.lng != null
    Column {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .size(8.dp)
                    .clip(CircleShape)
                    .background(if (hasFix) urgencyColors.low else urgencyColors.medium)
            )
            Spacer(Modifier.size(8.dp))
            Text(
                text = if (hasFix)
                    "GPS locked — your exact coordinates travel with the SOS"
                else
                    vm.locationStatus,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        // The one location problem the user cannot fix from this screen.
        if (vm.needsPreciseLocation) {
            TextButton(onClick = { openAppSettings(context) }) {
                Text("Allow precise location")
            }
        }
    }
}

private fun openAppSettings(context: Context) {
    val intent = Intent(
        Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
        Uri.fromParts("package", context.packageName, null)
    ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    try {
        context.startActivity(intent)
    } catch (e: Exception) {
        Log.w("VictimScreen", "cannot open app settings: ${e.message}")
    }
}

@Composable
private fun Field(label: String, content: @Composable () -> Unit) {
    Column(Modifier.padding(bottom = 18.dp)) {
        Text(
            label,
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.SemiBold,
            color = MaterialTheme.colorScheme.onBackground
        )
        Spacer(Modifier.height(8.dp))
        content()
    }
}

@Composable
private fun LocationCard(vm: MeshViewModel) {
    val la = vm.lat
    val lo = vm.lng
    val hasFix = la != null && lo != null
    Card(Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                Icons.Filled.Place,
                contentDescription = null,
                tint = if (hasFix) urgencyColors.low else MaterialTheme.colorScheme.onSurfaceVariant
            )
            Spacer(Modifier.size(12.dp))
            Column(Modifier.weight(1f)) {
                Text("GPS location", fontWeight = FontWeight.SemiBold)
                if (hasFix) {
                    // Six decimals is ~0.1 m — finer than any phone's GNSS accuracy,
                    // but it costs nothing to read and matches what gets transmitted.
                    Text("%.6f, %.6f".format(la, lo), style = MaterialTheme.typography.bodyLarge)
                    vm.fixTime?.let {
                        Text(
                            "updated ${relativeTime(it)}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
                Text(
                    vm.locationStatus,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            if (!hasFix) {
                TextButton(onClick = { vm.refreshLocation() }) {
                    Icon(Icons.Filled.Refresh, contentDescription = null)
                    Spacer(Modifier.size(4.dp))
                    Text("Retry")
                }
            }
        }
    }
}

@Composable
private fun StatusLadder(stage: Int, statusText: String) {
    Card(
        Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer
        )
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                statusText,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onPrimaryContainer
            )
            Spacer(Modifier.height(2.dp))
            Step("Sent from this phone", stage >= 0)
            Step("Reached the control room", stage >= 1)
            Step("Help is on the way", stage >= 2)
        }
    }
}

@Composable
private fun Step(label: String, done: Boolean) {
    val onContainer = MaterialTheme.colorScheme.onPrimaryContainer
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier
                .size(16.dp)
                .clip(CircleShape)
                .background(if (done) urgencyColors.low else Color.Transparent)
                .border(
                    width = if (done) 0.dp else 1.5.dp,
                    color = if (done) Color.Transparent else onContainer.copy(alpha = 0.4f),
                    shape = CircleShape
                ),
            contentAlignment = Alignment.Center
        ) {
            if (done) {
                Icon(
                    Icons.Filled.Check,
                    contentDescription = null,
                    tint = Color.White,
                    modifier = Modifier.size(12.dp)
                )
            }
        }
        Spacer(Modifier.size(10.dp))
        Text(
            label,
            color = if (done) onContainer else onContainer.copy(alpha = 0.5f),
            fontWeight = if (done) FontWeight.SemiBold else FontWeight.Normal
        )
    }
}
