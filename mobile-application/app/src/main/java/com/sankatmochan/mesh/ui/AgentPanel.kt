package com.sankatmochan.mesh.ui

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Mic
import androidx.compose.material.icons.rounded.Stop
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.sankatmochan.mesh.agent.SahayakAgent

/**
 * The post-SOS Sahayak conversation, designed for a person whose brain has gone blank:
 * big text, at most one question on screen, giant tap targets, tap-to-toggle voice.
 * Calm palette only — no red, no countdowns, no alarm iconography (the agent's rules).
 */
@Composable
fun AgentPanel(agent: SahayakAgent, modifier: Modifier = Modifier) {
    if (!agent.isEngaged) return

    // A live agent session keeps the screen on: the conversation, check-ins and the silent
    // escalation all die with a doze-killed process; light is cheaper than a missed rescue.
    val view = LocalView.current
    DisposableEffect(Unit) {
        view.keepScreenOn = true
        onDispose { view.keepScreenOn = false }
    }

    val context = LocalContext.current
    val micLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> if (granted) agent.toggleVoice() }

    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(
                "SAHAYAK · WITH YOU",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.primary,
                letterSpacing = 2.sp,
            )

            // The last few turns, newest last. Big and readable; the victim never scrolls.
            agent.messages.takeLast(4).forEach { m ->
                Text(
                    text = m.text.ifBlank { "…" },
                    style = if (m.fromAgent) MaterialTheme.typography.titleMedium
                    else MaterialTheme.typography.bodyMedium,
                    fontWeight = if (m.fromAgent) FontWeight.SemiBold else FontWeight.Normal,
                    color = if (m.fromAgent) MaterialTheme.colorScheme.onSurface
                    else MaterialTheme.colorScheme.onSurfaceVariant,
                    lineHeight = 26.sp,
                )
            }

            // Check-in: one giant, friendly button. Never alarming.
            AnimatedVisibility(visible = agent.checkInVisible) {
                Button(
                    onClick = { agent.onCheckInTap() },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(64.dp),
                ) {
                    Text("I'm okay", fontSize = 20.sp, fontWeight = FontWeight.Bold)
                }
            }

            // Quick answers: 2-4 giant tap targets for the current question.
            if (agent.quickReplies.isNotEmpty()) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    agent.quickReplies.forEach { reply ->
                        OutlinedButton(
                            onClick = { agent.onQuickReply(reply) },
                            modifier = Modifier
                                .weight(1f)
                                .height(56.dp),
                            contentPadding = ButtonDefaults.TextButtonContentPadding,
                        ) {
                            Text(reply.label, fontSize = 16.sp, maxLines = 1)
                        }
                    }
                }
            }

            // Voice answer: tap to talk, tap to stop (never hold — trembling hands).
            if (agent.phase == SahayakAgent.Phase.ACTIVE &&
                agent.voiceState != SahayakAgent.VoiceState.UNAVAILABLE
            ) {
                OutlinedButton(
                    onClick = {
                        val granted = ContextCompat.checkSelfPermission(
                            context, Manifest.permission.RECORD_AUDIO
                        ) == PackageManager.PERMISSION_GRANTED
                        if (granted) agent.toggleVoice()
                        else micLauncher.launch(Manifest.permission.RECORD_AUDIO)
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(56.dp),
                ) {
                    when (agent.voiceState) {
                        SahayakAgent.VoiceState.RECORDING -> {
                            Icon(Icons.Rounded.Stop, contentDescription = null)
                            Spacer(Modifier.width(8.dp))
                            Text("Listening… tap when done", fontSize = 16.sp)
                        }
                        SahayakAgent.VoiceState.TRANSCRIBING -> {
                            CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                            Spacer(Modifier.width(8.dp))
                            Text("One moment…", fontSize = 16.sp)
                        }
                        else -> {
                            Icon(Icons.Rounded.Mic, contentDescription = null)
                            Spacer(Modifier.width(8.dp))
                            Text("Answer by voice", fontSize = 16.sp)
                        }
                    }
                }
            }
        }
    }
}
