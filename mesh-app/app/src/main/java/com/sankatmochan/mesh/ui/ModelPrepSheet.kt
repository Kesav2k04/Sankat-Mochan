package com.sankatmochan.mesh.ui

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Bolt
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.CloudDownload
import androidx.compose.material.icons.rounded.DownloadForOffline
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.lifecycle.viewmodel.compose.viewModel
import com.sankatmochan.mesh.chat.AssistantModel
import com.sankatmochan.mesh.chat.AssistantModels
import com.sankatmochan.mesh.chat.ModelPrepViewModel
import com.sankatmochan.mesh.chat.ModelPrepViewModel.Phase

/**
 * "Prepare for offline" helper, reached from the info button on the home console. It coaxes the
 * user to download a safety-assistant model *now, while there's still signal*, so it's ready when
 * an emergency takes them offline - the whole point of an offline-first app. Recommends a model
 * for the device, then downloads it with a live progress bar and a rolling activity log.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ModelPrepSheet(onDismiss: () -> Unit) {
    val vm: ModelPrepViewModel = viewModel()
    LaunchedEffect(Unit) { vm.open() }

    Dialog(onDismissRequest = onDismiss) {
        Surface(
            shape = TileShape,
            color = MaterialTheme.colorScheme.surfaceContainerHigh,
        ) {
            Column(
                Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState())
                    .padding(20.dp)
            ) {
                // Header.
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconBadge(
                        Icons.Rounded.DownloadForOffline,
                        tint = MaterialTheme.colorScheme.primary,
                        size = 44.dp,
                    )
                    Spacer(Modifier.size(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(
                            "Be ready before you're offline",
                            style = MaterialTheme.typography.titleMedium,
                            color = MaterialTheme.colorScheme.onSurface,
                        )
                        Text(
                            "Download a safety assistant now, while you still have signal. In an " +
                                "emergency it answers first-aid and safety questions with no network.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            lineHeight = 18.sp,
                        )
                    }
                }

                Spacer(Modifier.height(18.dp))
                RecommendationCard(vm)

                Spacer(Modifier.height(16.dp))
                // The state-driven action area, cross-fading between phases for a smooth feel.
                AnimatedContent(
                    targetState = vm.phase,
                    transitionSpec = { fadeIn(tween(220)).togetherWith(fadeOut(tween(140))) },
                    label = "prepPhase",
                ) { phase ->
                    when (phase) {
                        Phase.CHECKING -> CenteredMini("Preparing…")

                        Phase.UNSUPPORTED -> Text(
                            "On-device AI needs a Snapdragon phone with the NPU runtime - it won't " +
                                "run here. Everything else in the app still works offline.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )

                        Phase.READY_TO_DOWNLOAD, Phase.FAILED -> Column {
                            if (phase == Phase.FAILED) {
                                Text(
                                    "That download didn't finish. Try again.",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.error,
                                )
                                Spacer(Modifier.height(10.dp))
                            }
                            SheetButton(
                                text = "Download ${vm.recommended.displayName} · ${vm.recommended.approxSize}",
                                icon = Icons.Rounded.CloudDownload,
                                onClick = { vm.download() },
                            )
                        }

                        Phase.DOWNLOADING -> Column {
                            LinearProgressIndicator(
                                progress = { vm.percent / 100f },
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .height(8.dp)
                                    .clip(CircleShape),
                                color = MaterialTheme.colorScheme.primary,
                                trackColor = MaterialTheme.colorScheme.surfaceContainerHighest,
                            )
                            Spacer(Modifier.height(8.dp))
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(
                                    "${vm.percent}%",
                                    style = MaterialTheme.typography.titleMedium,
                                    color = MaterialTheme.colorScheme.onSurface,
                                    modifier = Modifier.weight(1f),
                                )
                                TextButton(onClick = { vm.cancel() }) { Text("Cancel") }
                            }
                        }

                        Phase.ALREADY_READY, Phase.DONE -> ReadyRow(
                            if (phase == Phase.DONE) "Downloaded - ready offline"
                            else "Already downloaded - ready offline"
                        )
                    }
                }

                // Alternatives - only worth showing when a download hasn't started.
                if (vm.phase == Phase.READY_TO_DOWNLOAD || vm.phase == Phase.FAILED) {
                    Spacer(Modifier.height(16.dp))
                    SectionLabel("or pick another")
                    Spacer(Modifier.height(10.dp))
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        AssistantModels.catalog.forEach { model ->
                            OptionChip(
                                label = model.displayName,
                                selected = model.id == vm.recommended.id,
                            ) { vm.download(model) }
                        }
                    }
                }

                if (vm.log.isNotEmpty()) {
                    Spacer(Modifier.height(16.dp))
                    ActivityLog(vm.log)
                }

                Spacer(Modifier.height(12.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    TextButton(onClick = onDismiss) {
                        Text(if (vm.phase == Phase.DONE || vm.phase == Phase.ALREADY_READY) "Done" else "Close")
                    }
                }
            }
        }
    }
}

@Composable
private fun RecommendationCard(vm: ModelPrepViewModel) {
    val model: AssistantModel = vm.recommended
    Tile(
        Modifier.fillMaxWidth(),
        shape = TileShapeSmall,
        container = MaterialTheme.colorScheme.surfaceContainerHighest,
    ) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            IconBadge(Icons.Rounded.Bolt, tint = MaterialTheme.colorScheme.tertiary, size = 40.dp)
            Spacer(Modifier.size(12.dp))
            Column(Modifier.weight(1f)) {
                SectionLabel("recommended for your device")
                Spacer(Modifier.height(4.dp))
                Text(
                    "${model.displayName} · ${model.approxSize}",
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onSurface,
                )
                Text(
                    model.blurb,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    lineHeight = 16.sp,
                )
            }
        }
    }
}

@Composable
private fun ReadyRow(text: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(
            Icons.Rounded.CheckCircle,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.tertiary,
            modifier = Modifier.size(28.dp),
        )
        Spacer(Modifier.size(10.dp))
        Text(
            text,
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onSurface,
        )
    }
}

@Composable
private fun CenteredMini(text: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        CircularProgressIndicator(
            color = MaterialTheme.colorScheme.primary,
            strokeWidth = 2.5.dp,
            modifier = Modifier.size(20.dp),
        )
        Spacer(Modifier.size(12.dp))
        Text(
            text,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/** The rolling backend activity feed - shows what's happening in plain language (CLAUDE.md #10:
 *  status, not stack traces). Newest lines at the bottom, older ones dimmed. */
@Composable
private fun ActivityLog(lines: List<String>) {
    val scroll = rememberScrollState()
    LaunchedEffect(lines.size) { scroll.animateScrollTo(scroll.maxValue) }
    Box(
        Modifier
            .fillMaxWidth()
            .heightIn(max = 132.dp)
            .clip(TileShapeSmall)
            .background(MaterialTheme.colorScheme.surfaceContainerLowest)
            .padding(12.dp)
    ) {
        Column(Modifier.verticalScroll(scroll)) {
            lines.forEachIndexed { i, line ->
                Text(
                    line,
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace,
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(
                        alpha = if (i == lines.lastIndex) 1f else 0.6f
                    ),
                    lineHeight = 16.sp,
                )
            }
        }
    }
}

@Composable
private fun SheetButton(
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
        Text(text, style = MaterialTheme.typography.titleMedium, color = Color.White, fontWeight = FontWeight.Bold)
    }
}
