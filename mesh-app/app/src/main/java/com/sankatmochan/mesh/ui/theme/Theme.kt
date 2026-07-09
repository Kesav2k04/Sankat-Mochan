package com.sankatmochan.mesh.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Editorial light palette from the deck: off-white paper, near-black ink,
// one saffron/red accent for urgency.
private val Saffron = Color(0xFFB23A1E)
private val Ink = Color(0xFF1A1A1A)
private val Paper = Color(0xFFF7F4EF)

private val LightColors = lightColorScheme(
    primary = Saffron,
    onPrimary = Color.White,
    secondary = Color(0xFF3A5A6B),
    background = Paper,
    onBackground = Ink,
    surface = Color.White,
    onSurface = Ink,
    error = Color(0xFFC62828),
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFFE0653F),
    background = Color(0xFF121212),
    surface = Color(0xFF1E1E1E),
)

@Composable
fun SankatMochanTheme(
    useDarkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {
    MaterialTheme(
        colorScheme = if (useDarkTheme) DarkColors else LightColors,
        typography = Typography(),
        content = content
    )
}
