package com.sankatmochan.mesh.ui

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import android.util.Log
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.clickable
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
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material.icons.rounded.GraphicEq
import androidx.compose.material.icons.rounded.Mic
import androidx.compose.material.icons.rounded.MyLocation
import androidx.compose.material.icons.rounded.Podcasts
import androidx.compose.material.icons.rounded.Sos
import androidx.compose.material.icons.rounded.Tune
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
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
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sankatmochan.mesh.MeshViewModel
import com.sankatmochan.mesh.ui.theme.brandGradients
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
 * The SOS console. One tap on the hero tile sends; the bento underneath answers the two
 * questions a person in trouble actually has — "can anyone hear me?" and "do they know
 * where I am?" — without a word of jargon. Everything optional lives behind Details.
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

    // Acknowledgement, not a send lock: the button stays live, so a second tap always
    // gets through.
    LaunchedEffect(sent.size) {
        if (sent.isNotEmpty()) {
            justSent = true
            delay(2500)
            justSent = false
        }
    }

    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(Modifier.fillMaxSize()) {
            MeshTopBar("Send for help", "no signal needed", peers, onBack)
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Spacer(Modifier.height(0.dp))

                // An SOS already in flight outranks everything else.
                if (latest != null) {
                    ProgressTile(
                        stage = latest.stage,
                        statusText = latest.statusText,
                        count = sent.size,
                        modifier = Modifier.entrance(0)
                    )
                }

                SosTile(
                    justSent = justSent,
                    repeat = sent.isNotEmpty(),
                    withVoice = vm.pendingVoice != null,
                    modifier = Modifier.entrance(1),
                    onSend = { vm.sendSos(category, urgency, gist, lang, location) }
                )

                // Can anyone hear me? / Do they know where I am?
                Row(
                    Modifier.fillMaxWidth().entrance(2),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    StateTile(
                        modifier = Modifier.weight(1f),
                        icon = Icons.Rounded.Podcasts,
                        label = "mesh",
                        ok = peers > 0,
                        okText = "$peers in range",
                        waitText = "Searching…",
                        detail = if (peers > 0) "Goes out instantly"
                        else "Held until a link appears"
                    )
                    StateTile(
                        modifier = Modifier.weight(1f),
                        icon = Icons.Rounded.MyLocation,
                        label = "gps",
                        ok = vm.lat != null && vm.lng != null,
                        okText = "Locked",
                        waitText = "Searching…",
                        detail = if (vm.lat != null) "Rides with the SOS"
                        else "Needs open sky"
                    )
                }

                VoiceTile(vm, Modifier.entrance(3))

                // GPS problems the user can actually fix.
                if (vm.needsPreciseLocation) {
                    Row(
                        Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        StatusRow(
                            urgencyColors.medium,
                            "Only approximate location allowed",
                            Modifier.weight(1f)
                        )
                        val context = LocalContext.current
                        TextButton(onClick = { openAppSettings(context) }) {
                            Text("Fix")
                        }
                    }
                } else if (vm.lat == null) {
                    StatusRow(urgencyColors.medium, vm.locationStatus)
                }

                DetailsTile(
                    open = detailsOpen,
                    onToggle = { detailsOpen = !detailsOpen },
                    modifier = Modifier.entrance(4),
                ) {
                    Column(Modifier.padding(top = 4.dp)) {
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
                            DetailField(gist, { gist = it }, "e.g. two children with me")
                        }
                        Field("Landmark near you") {
                            DetailField(location, { location = it }, "e.g. Sector 4, near the temple")
                        }
                        CoordinatesRow(vm)
                    }
                }

                Spacer(Modifier.height(16.dp))
            }
        }
    }
}

/**
 * The hero — a full-width rounded SOS surface in the signal red, white icon-circle top
 * left (the reference-2 signature), the word doing the rest. Press compresses on a
 * spring; a slow glow breathes behind it; SENT flips it green with a tick.
 */
@Composable
private fun SosTile(
    justSent: Boolean,
    repeat: Boolean,
    withVoice: Boolean,
    modifier: Modifier = Modifier,
    onSend: () -> Unit,
) {
    val gradients = brandGradients
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val scale by animateFloatAsState(if (pressed) 0.965f else 1f, Motion.touchSpring, label = "sosScale")

    val infinite = rememberInfiniteTransition(label = "sosBreath")
    val glowAlpha by infinite.animateFloat(
        initialValue = 0.45f, targetValue = 0.18f,
        animationSpec = infiniteRepeatable(tween(1700), RepeatMode.Reverse),
        label = "sosGlowAlpha"
    )

    val glow by animateColorAsState(
        if (justSent) urgencyColors.low else gradients.sosGlow,
        tween(Motion.Mid), label = "sosGlowColor"
    )
    val fill = when {
        justSent -> gradients.safe
        pressed -> gradients.sosPressed
        else -> gradients.sos
    }

    Box(
        modifier = modifier
            .fillMaxWidth()
            .height(196.dp)
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .softGlow(glow, TileShape, elevation = 30.dp, alpha = glowAlpha)
            .clip(TileShape)
            .background(fill)
            .clickable(interactionSource = interaction, indication = null, onClick = onSend)
            .semantics { contentDescription = "Send an emergency SOS" },
    ) {
        Column(Modifier.fillMaxSize().padding(20.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier
                        .size(46.dp)
                        .clip(CircleShape)
                        .background(Color.White),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        if (justSent) Icons.Rounded.Check else Icons.Rounded.Sos,
                        contentDescription = null,
                        tint = if (justSent) urgencyColors.low else MaterialTheme.colorScheme.primary,
                        modifier = Modifier.size(24.dp)
                    )
                }
                Spacer(Modifier.weight(1f))
                Text(
                    text = when {
                        justSent -> "DELIVERING"
                        withVoice -> "VOICE ATTACHED"
                        repeat -> "RESEND"
                        else -> "READY"
                    },
                    style = MaterialTheme.typography.labelSmall,
                    color = Color.White.copy(alpha = 0.85f)
                )
            }
            Spacer(Modifier.weight(1f))
            Text(
                text = if (justSent) "SENT" else "SOS",
                color = Color.White,
                fontSize = 52.sp,
                fontWeight = FontWeight.Black,
                letterSpacing = 2.sp,
            )
            Text(
                text = when {
                    justSent -> "Your call is on the mesh"
                    withVoice -> "Tap to send with your voice message"
                    repeat -> "Tap to send again"
                    else -> "Tap once — location goes with it"
                },
                style = MaterialTheme.typography.bodyMedium,
                color = Color.White.copy(alpha = 0.88f)
            )
        }
    }
}

/** A bento state cell: icon badge, tracked caption, bold value, one-line detail. */
@Composable
private fun StateTile(
    modifier: Modifier,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    label: String,
    ok: Boolean,
    okText: String,
    waitText: String,
    detail: String,
) {
    val tint = if (ok) urgencyColors.low else urgencyColors.medium
    Tile(modifier = modifier.height(150.dp)) {
        Column(Modifier.fillMaxSize().padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconBadge(icon, tint = tint, size = 34.dp)
                Spacer(Modifier.weight(1f))
                Box(
                    Modifier
                        .size(8.dp)
                        .clip(CircleShape)
                        .background(tint)
                )
            }
            Spacer(Modifier.weight(1f))
            SectionLabel(label)
            Text(
                if (ok) okText else waitText,
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onSurface
            )
            Text(
                detail,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                lineHeight = 15.sp,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis
            )
        }
    }
}

/**
 * Hold to speak, release to attach. The 5-second cap is airtime budget, not a nicety:
 * a 5 s Opus clip is ~22 LoRa frames, during which nobody else's SOS gets through.
 */
@Composable
private fun VoiceTile(vm: MeshViewModel, modifier: Modifier = Modifier) {
    val recording = vm.isRecording
    val attached = vm.pendingVoice != null
    var remaining by remember { mutableIntStateOf(MAX_VOICE_SECONDS) }

    LaunchedEffect(recording) {
        if (!recording) { remaining = MAX_VOICE_SECONDS; return@LaunchedEffect }
        remaining = MAX_VOICE_SECONDS
        while (remaining > 0) {
            delay(1000)
            remaining--
        }
        vm.stopRecording()
    }

    val infinite = rememberInfiniteTransition(label = "recPulse")
    val pulse by infinite.animateFloat(
        initialValue = 1f, targetValue = 0.55f,
        animationSpec = infiniteRepeatable(tween(550), RepeatMode.Reverse),
        label = "recPulseAlpha"
    )

    val container by animateColorAsState(
        when {
            recording -> MaterialTheme.colorScheme.primary
            attached -> urgencyColors.low.copy(alpha = 0.12f)
            else -> MaterialTheme.colorScheme.surfaceContainer
        },
        tween(Motion.Fast), label = "voiceBg"
    )

    Tile(
        modifier = modifier.fillMaxWidth(),
        container = container,
        stroke = when {
            recording -> Color.Transparent
            attached -> urgencyColors.low.copy(alpha = 0.4f)
            else -> MaterialTheme.colorScheme.outlineVariant
        },
    ) {
        Column {
            Row(
                Modifier
                    .fillMaxWidth()
                    .pointerInput(Unit) {
                        detectTapGestures(
                            onPress = {
                                vm.startRecording()
                                val completed = tryAwaitRelease()
                                if (completed) vm.stopRecording() else vm.cancelRecording()
                            }
                        )
                    }
                    .padding(14.dp)
                    .semantics { contentDescription = "Hold to record a voice message" },
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconBadge(
                    if (recording) Icons.Rounded.GraphicEq else Icons.Rounded.Mic,
                    tint = when {
                        recording -> Color.White.copy(alpha = pulse)
                        attached -> urgencyColors.low
                        else -> MaterialTheme.colorScheme.onSurfaceVariant
                    },
                    container = if (recording) Color.White.copy(alpha = 0.2f)
                    else if (attached) urgencyColors.low.copy(alpha = 0.16f)
                    else MaterialTheme.colorScheme.surfaceContainerHighest,
                    size = 40.dp
                )
                Spacer(Modifier.size(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        text = when {
                            recording -> "Recording · release to attach"
                            attached -> "Voice message attached"
                            else -> "Hold to add your voice"
                        },
                        style = MaterialTheme.typography.titleMedium,
                        color = if (recording) Color.White else MaterialTheme.colorScheme.onSurface
                    )
                    Text(
                        text = when {
                            recording -> "$remaining seconds left"
                            attached -> "${vm.pendingVoiceBytes} bytes · sends with your SOS"
                            else -> "5 seconds · travels with the SOS"
                        },
                        style = MaterialTheme.typography.bodySmall,
                        color = if (recording) Color.White.copy(alpha = 0.85f)
                        else MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                if (attached && !recording) {
                    TextButton(onClick = { vm.discardVoice() }) { Text("Remove") }
                }
            }
            // Countdown rail while recording.
            if (recording) {
                val fraction = remaining / MAX_VOICE_SECONDS.toFloat()
                Box(
                    Modifier
                        .fillMaxWidth()
                        .height(4.dp)
                        .background(Color.White.copy(alpha = 0.25f))
                ) {
                    Box(
                        Modifier
                            .fillMaxWidth(fraction)
                            .height(4.dp)
                            .background(Color.White)
                    )
                }
            }
        }
    }
    if (vm.voiceStatus.isNotBlank() && !recording && !attached) {
        Text(
            vm.voiceStatus,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(start = 4.dp, top = 6.dp)
        )
    }
}

/** Expandable details drawer, as a tile. Chevron rotates; content unfolds. */
@Composable
private fun DetailsTile(
    open: Boolean,
    onToggle: () -> Unit,
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    val rotation by animateFloatAsState(if (open) 90f else 0f, tween(Motion.Mid), label = "chev")
    Tile(modifier = modifier.fillMaxWidth()) {
        Column {
            Row(
                Modifier
                    .fillMaxWidth()
                    .clickable(onClick = onToggle)
                    .padding(14.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconBadge(
                    Icons.Rounded.Tune,
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    container = MaterialTheme.colorScheme.surfaceContainerHighest,
                    size = 40.dp
                )
                Spacer(Modifier.size(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        "Details",
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Text(
                        "Optional — category, language, landmark",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                Icon(
                    Icons.Rounded.ChevronRight,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.rotate(rotation)
                )
            }
            AnimatedVisibility(
                visible = open,
                enter = expandVertically(tween(Motion.Mid)) + fadeIn(tween(Motion.Mid)),
                exit = shrinkVertically(tween(Motion.Fast)) + fadeOut(tween(Motion.Fast)),
            ) {
                Box(Modifier.padding(horizontal = 14.dp)) { content() }
            }
        }
    }
}

@Composable
private fun Field(label: String, content: @Composable () -> Unit) {
    Column(Modifier.fillMaxWidth().padding(bottom = 18.dp)) {
        SectionLabel(label)
        Spacer(Modifier.height(10.dp))
        content()
    }
}

@Composable
private fun DetailField(value: String, onValueChange: (String) -> Unit, placeholder: String) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        placeholder = {
            Text(placeholder, color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f))
        },
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = MaterialTheme.colorScheme.primary,
            unfocusedBorderColor = MaterialTheme.colorScheme.outline,
            focusedContainerColor = MaterialTheme.colorScheme.surfaceContainerHigh,
            unfocusedContainerColor = MaterialTheme.colorScheme.surfaceContainerHigh,
            cursorColor = MaterialTheme.colorScheme.primary,
        )
    )
}

/** The raw fix — the audit trail, tucked at the bottom of Details. */
@Composable
private fun CoordinatesRow(vm: MeshViewModel) {
    val la = vm.lat
    val lo = vm.lng
    Column(Modifier.padding(bottom = 16.dp)) {
        SectionLabel("gps fix")
        Spacer(Modifier.height(6.dp))
        if (la != null && lo != null) {
            Text(
                "%.6f, %.6f".format(la, lo),
                style = MaterialTheme.typography.bodyMedium,
                fontFamily = FontFamily.Monospace,
                color = MaterialTheme.colorScheme.onSurface
            )
            vm.fixTime?.let {
                Text(
                    "updated ${relativeTime(it)}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        } else {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    vm.locationStatus,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.weight(1f)
                )
                TextButton(onClick = { vm.refreshLocation() }) { Text("Retry") }
            }
        }
    }
}

/** Three-step journey of the latest SOS, horizontal. */
@Composable
private fun ProgressTile(stage: Int, statusText: String, count: Int, modifier: Modifier = Modifier) {
    Tile(
        modifier = modifier.fillMaxWidth(),
        container = MaterialTheme.colorScheme.primaryContainer,
        stroke = MaterialTheme.colorScheme.primary.copy(alpha = 0.35f),
    ) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    statusText,
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onPrimaryContainer,
                    modifier = Modifier.weight(1f)
                )
                if (count > 1) {
                    SectionLabel("×$count", color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.7f))
                }
            }
            Spacer(Modifier.height(14.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                StepDot(done = stage >= 0)
                StepLine(done = stage >= 1)
                StepDot(done = stage >= 1)
                StepLine(done = stage >= 2)
                StepDot(done = stage >= 2)
            }
            Spacer(Modifier.height(8.dp))
            Row {
                StepLabel("Sent", stage >= 0, Modifier.weight(1f), TextAlign.Start)
                StepLabel("Control room", stage >= 1, Modifier.weight(1f), TextAlign.Center)
                StepLabel("Help coming", stage >= 2, Modifier.weight(1f), TextAlign.End)
            }
        }
    }
}

@Composable
private fun StepDot(done: Boolean) {
    val fill by animateColorAsState(
        if (done) urgencyColors.low else MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.2f),
        tween(Motion.Mid), label = "stepDot"
    )
    Box(
        Modifier
            .size(20.dp)
            .clip(CircleShape)
            .background(fill),
        contentAlignment = Alignment.Center
    ) {
        if (done) {
            Icon(
                Icons.Rounded.Check,
                contentDescription = null,
                tint = Color.White,
                modifier = Modifier.size(12.dp)
            )
        }
    }
}

@Composable
private fun androidx.compose.foundation.layout.RowScope.StepLine(done: Boolean) {
    val fill by animateColorAsState(
        if (done) urgencyColors.low else MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.15f),
        tween(Motion.Mid), label = "stepLine"
    )
    Box(
        Modifier
            .weight(1f)
            .height(3.dp)
            .padding(horizontal = 4.dp)
            .clip(CircleShape)
            .background(fill)
    )
}

@Composable
private fun StepLabel(text: String, done: Boolean, modifier: Modifier, align: TextAlign) {
    Text(
        text,
        style = MaterialTheme.typography.labelSmall,
        color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = if (done) 1f else 0.5f),
        modifier = modifier,
        textAlign = align
    )
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
