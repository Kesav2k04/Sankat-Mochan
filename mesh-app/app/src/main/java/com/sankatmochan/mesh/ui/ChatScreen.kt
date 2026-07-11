package com.sankatmochan.mesh.ui

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.Send
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.ChevronLeft
import androidx.compose.material.icons.rounded.CloudDownload
import androidx.compose.material.icons.rounded.DeleteSweep
import androidx.compose.material.icons.rounded.Stop
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.sankatmochan.mesh.chat.AssistantModel
import com.sankatmochan.mesh.chat.AssistantModels
import com.sankatmochan.mesh.chat.ChatViewModel
import com.sankatmochan.mesh.chat.ChatViewModel.Phase
import com.sankatmochan.mesh.chat.ChatViewModel.Role
import com.sankatmochan.mesh.ui.theme.urgencyColors

/**
 * The on-device AI assistant page. Reached from the chat chip on the home console. Everything
 * runs offline on the phone once a small model has been pulled once; the model lifecycle and
 * all Qualcomm GenieX calls live in [ChatViewModel] / GenieXEngine.
 */
@Composable
fun ChatScreen(onBack: () -> Unit) {
    val vm: ChatViewModel = viewModel()

    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(Modifier.fillMaxSize()) {
            ChatHeader(vm = vm, onBack = onBack)
            Box(Modifier.fillMaxWidth().weight(1f)) {
                if (vm.phase == Phase.READY) {
                    Conversation(vm)
                } else {
                    SetupPanel(vm)
                }
            }
            if (vm.phase == Phase.READY) {
                InputBar(
                    isGenerating = vm.isGenerating,
                    onSend = vm::send,
                    onStop = vm::stop,
                )
            }
        }
    }
}

/** Back chip, title, and (when a chat is live) a clear-conversation action. */
@Composable
private fun ChatHeader(vm: ChatViewModel, onBack: () -> Unit) {
    val caption = when (vm.phase) {
        Phase.READY -> "${vm.selectedModel.displayName} · ${if (vm.runOnNpu) "NPU" else "CPU"} · offline"
        Phase.UNSUPPORTED -> "unavailable on this device"
        else -> "on-device · no cloud"
    }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        TopBarChip(icon = Icons.Rounded.ChevronLeft, description = "Back", onClick = onBack)
        Spacer(Modifier.size(14.dp))
        Box(
            Modifier
                .size(40.dp)
                .clip(CircleShape)
                .background(MaterialTheme.colorScheme.primary.copy(alpha = 0.16f)),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                Icons.Rounded.AutoAwesome,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(22.dp)
            )
        }
        Spacer(Modifier.size(12.dp))
        Column(Modifier.weight(1f)) {
            Text(
                "Sahayak",
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.onBackground,
                maxLines = 1
            )
            Text(
                caption.uppercase(),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1
            )
        }
        if (vm.phase == Phase.READY) {
            TopBarChip(
                icon = Icons.Rounded.DeleteSweep,
                description = "Clear conversation",
                onClick = vm::clearChat,
            )
        }
    }
}

// ── Setup (init / download / load / errors) ───────────────────────────────────

@Composable
private fun SetupPanel(vm: ChatViewModel) {
    Column(
        Modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Spacer(Modifier.height(4.dp))
        when (vm.phase) {
            Phase.INITIALIZING -> CenteredStatus("Waking the assistant…", spinner = true)

            Phase.UNSUPPORTED -> InfoTile(
                title = "Not available here",
                body = vm.statusMessage.ifBlank {
                    "On-device AI needs a Snapdragon phone with the NPU runtime. It won't run " +
                        "on an emulator."
                },
                tone = InfoTone.MUTED,
            )

            Phase.LOADING -> CenteredStatus(
                "Loading ${vm.selectedModel.displayName} onto the ${if (vm.runOnNpu) "NPU" else "CPU"}…",
                spinner = true,
            )

            Phase.DOWNLOADING -> DownloadCard(vm)

            Phase.NEEDS_MODEL, Phase.LOAD_FAILED -> ChooseModelCard(vm)

            Phase.READY -> Unit // handled by Conversation
        }
    }
}

@Composable
private fun ChooseModelCard(vm: ChatViewModel) {
    Tile(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconBadge(Icons.Rounded.AutoAwesome, tint = MaterialTheme.colorScheme.primary, size = 40.dp)
                Spacer(Modifier.size(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        "Offline AI assistant",
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Text(
                        "Downloads once, then answers with no signal.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            Spacer(Modifier.height(16.dp))
            SectionLabel("Choose a model")
            Spacer(Modifier.height(10.dp))
            ChipRow(
                options = AssistantModels.catalog.map { it.id to it.displayName },
                selected = vm.selectedModel.id,
                onSelect = { id -> AssistantModels.byId(id)?.let(vm::selectModel) },
            )

            Spacer(Modifier.height(12.dp))
            Text(
                "${vm.selectedModel.blurb}  (${vm.selectedModel.approxSize})",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                lineHeight = 18.sp,
            )

            Spacer(Modifier.height(16.dp))
            SectionLabel("Run on")
            Spacer(Modifier.height(10.dp))
            ChipRow(
                options = listOf("npu" to "NPU (fast)", "cpu" to "CPU (fallback)"),
                selected = if (vm.runOnNpu) "npu" else "cpu",
                onSelect = { vm.chooseCompute(it == "npu") },
            )

            if (vm.phase == Phase.LOAD_FAILED) {
                Spacer(Modifier.height(14.dp))
                Text(
                    vm.statusMessage.ifBlank { "Could not start the model." },
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                )
            }

            Spacer(Modifier.height(18.dp))
            val loadFailed = vm.phase == Phase.LOAD_FAILED
            PrimaryButton(
                text = if (loadFailed) "Try again" else "Download & start",
                icon = Icons.Rounded.CloudDownload,
                onClick = { if (loadFailed) vm.retryLoad() else vm.download() },
            )
        }
    }
}

@Composable
private fun DownloadCard(vm: ChatViewModel) {
    Tile(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconBadge(Icons.Rounded.CloudDownload, tint = MaterialTheme.colorScheme.secondary, size = 40.dp)
                Spacer(Modifier.size(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        "Downloading ${vm.selectedModel.displayName}",
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Text(
                        "${vm.downloadPercent}% · ${vm.selectedModel.approxSize} · keep this screen open",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            Spacer(Modifier.height(16.dp))
            LinearProgressIndicator(
                progress = { vm.downloadPercent / 100f },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(8.dp)
                    .clip(CircleShape),
                color = MaterialTheme.colorScheme.primary,
                trackColor = MaterialTheme.colorScheme.surfaceContainerHighest,
            )
            Spacer(Modifier.height(8.dp))
            TextButton(onClick = vm::cancelDownload) { Text("Cancel") }
        }
    }
}

private enum class InfoTone { MUTED, ERROR }

@Composable
private fun InfoTile(title: String, body: String, tone: InfoTone) {
    val accent = when (tone) {
        InfoTone.MUTED -> MaterialTheme.colorScheme.onSurfaceVariant
        InfoTone.ERROR -> MaterialTheme.colorScheme.error
    }
    Tile(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, color = accent)
            Spacer(Modifier.height(8.dp))
            Text(
                body,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                lineHeight = 20.sp,
            )
        }
    }
}

@Composable
private fun CenteredStatus(text: String, spinner: Boolean) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            if (spinner) {
                CircularProgressIndicator(
                    color = MaterialTheme.colorScheme.primary,
                    strokeWidth = 3.dp,
                    modifier = Modifier.size(36.dp),
                )
                Spacer(Modifier.height(18.dp))
            }
            Text(
                text,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun PrimaryButton(
    text: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    onClick: () -> Unit,
) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(TileShapeSmall)
            .background(MaterialTheme.colorScheme.primary)
            .bounceClick(pressedScale = 0.97f, onClick = onClick)
            .padding(vertical = 14.dp),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, contentDescription = null, tint = Color.White, modifier = Modifier.size(20.dp))
        Spacer(Modifier.size(10.dp))
        Text(
            text,
            style = MaterialTheme.typography.titleMedium,
            color = Color.White,
            fontWeight = FontWeight.Bold,
        )
    }
}

// ── Conversation ──────────────────────────────────────────────────────────────

@Composable
private fun Conversation(vm: ChatViewModel) {
    val listState = rememberLazyListState()
    val lastText = vm.messages.lastOrNull()?.text?.length ?: 0

    // Ride the bottom as messages arrive and as the streaming answer grows.
    LaunchedEffect(vm.messages.size, lastText) {
        if (vm.messages.isNotEmpty()) {
            listState.animateScrollToItem(vm.messages.lastIndex)
        }
    }

    LazyColumn(
        state = listState,
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        items(vm.messages) { msg -> MessageBubble(msg) }
    }
}

@Composable
private fun MessageBubble(msg: ChatViewModel.UiMessage) {
    val isUser = msg.role == Role.USER
    val container = when {
        msg.isError -> MaterialTheme.colorScheme.errorContainer
        isUser -> MaterialTheme.colorScheme.secondaryContainer
        else -> MaterialTheme.colorScheme.surfaceContainerHigh
    }
    val textColor = when {
        msg.isError -> MaterialTheme.colorScheme.onErrorContainer
        isUser -> MaterialTheme.colorScheme.onSecondaryContainer
        else -> MaterialTheme.colorScheme.onSurface
    }
    val shape = RoundedCornerShape(
        topStart = 18.dp,
        topEnd = 18.dp,
        bottomStart = if (isUser) 18.dp else 6.dp,
        bottomEnd = if (isUser) 6.dp else 18.dp,
    )
    val thinking = msg.streaming && msg.text.isEmpty()

    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start
    ) {
        Box(
            Modifier
                .widthIn(max = 320.dp)
                .clip(shape)
                .background(container)
                .padding(horizontal = 14.dp, vertical = 10.dp)
        ) {
            if (thinking) {
                ThinkingDots(color = textColor.copy(alpha = 0.7f))
            } else {
                // Model output is rendered as PLAIN TEXT — never as HTML (CLAUDE.md #9).
                Text(
                    text = msg.text,
                    style = MaterialTheme.typography.bodyMedium,
                    color = textColor,
                    lineHeight = 20.sp,
                )
            }
        }
    }
}

/** Three breathing dots while the first token is still on its way. */
@Composable
private fun ThinkingDots(color: Color) {
    val transition = rememberInfiniteTransition(label = "think")
    Row(verticalAlignment = Alignment.CenterVertically) {
        repeat(3) { i ->
            val alpha by transition.animateFloat(
                initialValue = 0.25f,
                targetValue = 1f,
                animationSpec = infiniteRepeatable(
                    tween(600, delayMillis = i * 160),
                    RepeatMode.Reverse,
                ),
                label = "dot$i",
            )
            Box(
                Modifier
                    .padding(horizontal = 3.dp)
                    .size(7.dp)
                    .clip(CircleShape)
                    .background(color.copy(alpha = alpha))
            )
        }
    }
}

// ── Input ─────────────────────────────────────────────────────────────────────

@Composable
private fun InputBar(
    isGenerating: Boolean,
    onSend: (String) -> Unit,
    onStop: () -> Unit,
) {
    var text by remember { mutableStateOf("") }
    val canSend = text.isNotBlank() && !isGenerating

    val submit = {
        if (text.isNotBlank() && !isGenerating) {
            onSend(text)
            text = ""
        }
    }

    Row(
        Modifier
            .fillMaxWidth()
            .imePadding()
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.Bottom,
    ) {
        OutlinedTextField(
            value = text,
            onValueChange = { text = it },
            modifier = Modifier.weight(1f),
            placeholder = {
                Text(
                    "Ask Sahayak anything…",
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f)
                )
            },
            shape = RoundedCornerShape(22.dp),
            maxLines = 4,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
            keyboardActions = KeyboardActions(onSend = { submit() }),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = MaterialTheme.colorScheme.primary,
                unfocusedBorderColor = MaterialTheme.colorScheme.outline,
                focusedContainerColor = MaterialTheme.colorScheme.surfaceContainerHigh,
                unfocusedContainerColor = MaterialTheme.colorScheme.surfaceContainerHigh,
                cursorColor = MaterialTheme.colorScheme.primary,
            ),
        )
        Spacer(Modifier.size(10.dp))
        SendOrStopButton(
            isGenerating = isGenerating,
            canSend = canSend,
            onSend = submit,
            onStop = onStop,
        )
    }
}

@Composable
private fun SendOrStopButton(
    isGenerating: Boolean,
    canSend: Boolean,
    onSend: () -> Unit,
    onStop: () -> Unit,
) {
    val bg = when {
        isGenerating -> MaterialTheme.colorScheme.surfaceContainerHighest
        canSend -> MaterialTheme.colorScheme.primary
        else -> MaterialTheme.colorScheme.surfaceContainerHigh
    }
    val tint = when {
        isGenerating -> MaterialTheme.colorScheme.onSurface
        canSend -> Color.White
        else -> MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
    }
    Box(
        Modifier
            .size(52.dp)
            .clip(CircleShape)
            .background(bg)
            .bounceClick(pressedScale = 0.9f, enabled = isGenerating || canSend) {
                if (isGenerating) onStop() else onSend()
            },
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            if (isGenerating) Icons.Rounded.Stop else Icons.AutoMirrored.Rounded.Send,
            contentDescription = if (isGenerating) "Stop" else "Send",
            tint = tint,
            modifier = Modifier.size(24.dp),
        )
    }
}
