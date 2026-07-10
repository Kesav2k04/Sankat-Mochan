package com.sankatmochan.mesh.ui

import android.media.MediaPlayer
import android.util.Log
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Card
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.sankatmochan.mesh.mesh.VoiceClip
import com.sankatmochan.mesh.ui.theme.urgencyColors

private const val TAG = "VoiceClips"

/**
 * A voice message from the mesh.
 *
 * Playback is offered only once every chunk has arrived. There is no retransmission on
 * the LoRa link today, so a clip with a hole in it is a corrupt Ogg container — handing
 * that to MediaPlayer would fail in front of a rescuer. Showing "19 of 22 pieces" is the
 * honest state, and it tells the operator the link is lossy rather than the app broken.
 */
@Composable
fun VoiceClipCard(clip: VoiceClip, modifier: Modifier = Modifier) {
    var player by remember { mutableStateOf<MediaPlayer?>(null) }
    var playing by remember { mutableStateOf(false) }

    // A MediaPlayer holds a codec; never let one outlive the card that owns it.
    DisposableEffect(clip.clipId) {
        onDispose {
            player?.run { runCatching { release() } }
            player = null
        }
    }

    Card(modifier.fillMaxWidth()) {
        Row(
            Modifier.padding(14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                Icons.Filled.Mic,
                contentDescription = null,
                tint = if (clip.complete) urgencyColors.critical
                else MaterialTheme.colorScheme.onSurfaceVariant
            )
            Spacer(Modifier.size(12.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    "Voice message from ${clip.origin}",
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.titleSmall
                )
                Spacer(Modifier.height(2.dp))
                Text(
                    text = if (clip.complete) routeLabel(clip.hops)
                    else "receiving — ${clip.received} of ${clip.total} pieces " +
                        "(${clip.missing} still missing)",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                if (!clip.complete) {
                    Spacer(Modifier.height(6.dp))
                    Progress(clip.received.toFloat() / clip.total)
                }
            }

            if (clip.complete) {
                Spacer(Modifier.size(10.dp))
                Box(
                    modifier = Modifier
                        .size(52.dp)
                        .clip(RoundedCornerShape(12.dp))
                        .background(urgencyColors.low)
                        .clickable {
                            if (playing) {
                                player?.run { runCatching { stop(); release() } }
                                player = null
                                playing = false
                            } else {
                                player = startPlayback(clip) { playing = false; player = null }
                                playing = player != null
                            }
                        },
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        Icons.Filled.PlayArrow,
                        contentDescription = if (playing) "Stop" else "Play voice message",
                        tint = Color.White
                    )
                }
            }
        }
    }
}

private fun startPlayback(clip: VoiceClip, onDone: () -> Unit): MediaPlayer? {
    val file = clip.file ?: return null
    return try {
        MediaPlayer().apply {
            setDataSource(file.absolutePath)
            setOnCompletionListener { runCatching { release() }; onDone() }
            setOnErrorListener { _, what, extra ->
                Log.w(TAG, "playback failed ($what/$extra) for ${clip.clipId}")
                runCatching { release() }
                onDone()
                true
            }
            prepare()
            start()
        }
    } catch (e: Exception) {
        Log.w(TAG, "could not play ${clip.clipId}: ${e.message}")
        onDone()
        null
    }
}

@Composable
private fun Progress(fraction: Float) {
    Box(
        Modifier
            .fillMaxWidth()
            .height(4.dp)
            .clip(RoundedCornerShape(2.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant)
    ) {
        Box(
            Modifier
                .fillMaxWidth(fraction.coerceIn(0f, 1f))
                .height(4.dp)
                .clip(RoundedCornerShape(2.dp))
                .background(urgencyColors.medium)
        )
    }
}
