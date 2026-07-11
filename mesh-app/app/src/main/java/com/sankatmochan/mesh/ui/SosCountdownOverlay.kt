package com.sankatmochan.mesh.ui

import androidx.compose.foundation.background
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sankatmochan.mesh.ui.theme.urgencyColors
import kotlinx.coroutines.delay

/**
 * The full-screen SOS countdown raised by the flip gesture (see SosGestureService). It gives the user
 * [totalSeconds] to decide: **Send now** fires immediately, **Cancel** backs out (and the caller
 * exits the app), and if they do nothing the SOS sends automatically at zero — the point of a
 * panic trigger is that a person who *can't* act still gets help out.
 *
 * Deliberately loud and single-purpose: one giant ticking number, two unmistakable buttons.
 */
@Composable
fun SosCountdownOverlay(
    totalSeconds: Int = 30,
    onSend: () -> Unit,
    onCancel: () -> Unit,
) {
    var remaining by remember { mutableIntStateOf(totalSeconds) }

    // One-way ticker: count down once, then auto-send. `onSend` is read fresh at fire time.
    LaunchedEffect(Unit) {
        while (remaining > 0) {
            delay(1_000)
            remaining--
        }
        onSend()
    }

    Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(
            Modifier
                .fillMaxSize()
                .padding(28.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Text(
                "EMERGENCY SOS",
                style = MaterialTheme.typography.labelMedium,
                color = urgencyColors.critical,
            )
            Spacer(Modifier.height(24.dp))

            // Ticking ring with the seconds left in the centre.
            Box(contentAlignment = Alignment.Center) {
                CircularProgressIndicator(
                    progress = { remaining / totalSeconds.toFloat() },
                    modifier = Modifier.size(220.dp),
                    color = urgencyColors.critical,
                    trackColor = MaterialTheme.colorScheme.surfaceContainerHigh,
                    strokeWidth = 10.dp,
                )
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        "$remaining",
                        fontSize = 88.sp,
                        fontWeight = FontWeight.Black,
                        color = MaterialTheme.colorScheme.onBackground,
                    )
                    Text(
                        "seconds",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            Spacer(Modifier.height(28.dp))
            Text(
                "Sending an SOS to nearby responders automatically.",
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onBackground,
                textAlign = TextAlign.Center,
            )
            Spacer(Modifier.height(8.dp))
            Text(
                "Your live location goes with it. Cancel if you're safe.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
            )

            Spacer(Modifier.height(36.dp))
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                CountdownButton(
                    text = "Cancel",
                    fill = MaterialTheme.colorScheme.surfaceContainerHigh,
                    textColor = MaterialTheme.colorScheme.onSurface,
                    modifier = Modifier.weight(1f),
                    onClick = onCancel,
                )
                CountdownButton(
                    text = "Send now",
                    fill = urgencyColors.critical,
                    textColor = Color.White,
                    modifier = Modifier.weight(1f),
                    onClick = onSend,
                )
            }
        }
    }
}

@Composable
private fun CountdownButton(
    text: String,
    fill: Color,
    textColor: Color,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    Box(
        modifier
            .clip(RoundedCornerShape(18.dp))
            .background(fill)
            .bounceClick(pressedScale = 0.96f, onClick = onClick)
            .padding(vertical = 18.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text,
            style = MaterialTheme.typography.titleMedium,
            color = textColor,
            fontWeight = FontWeight.Bold,
        )
    }
}
