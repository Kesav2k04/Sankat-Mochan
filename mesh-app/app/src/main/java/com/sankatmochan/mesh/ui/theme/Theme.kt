package com.sankatmochan.mesh.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

// Editorial light palette from the deck: off-white paper, near-black ink,
// one saffron/red accent for urgency.
private val Saffron = Color(0xFFB23A1E)
private val SaffronDark = Color(0xFFE0653F)
private val Ink = Color(0xFF1A1A1A)
private val Paper = Color(0xFFF7F4EF)
private val Slate = Color(0xFF3A5A6B)

private val LightColors = lightColorScheme(
    primary = Saffron,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFFFDBD1),
    onPrimaryContainer = Color(0xFF3B0A00),
    secondary = Slate,
    onSecondary = Color.White,
    background = Paper,
    onBackground = Ink,
    surface = Color.White,
    onSurface = Ink,
    surfaceVariant = Color(0xFFEDE7E0),
    onSurfaceVariant = Color(0xFF52453F),
    outline = Color(0xFF857269),
    error = Color(0xFFC62828),
    onError = Color.White,
)

// Previously only four roles were set here, so every colour the app did not name
// fell back to M3's stock purple. That is why dark mode looked like a different app.
private val DarkColors = darkColorScheme(
    primary = SaffronDark,
    onPrimary = Color(0xFF5C1900),
    primaryContainer = Color(0xFF802A12),
    onPrimaryContainer = Color(0xFFFFDBD1),
    secondary = Color(0xFF9FC6DA),
    onSecondary = Color(0xFF06344A),
    background = Color(0xFF121212),
    onBackground = Color(0xFFECE0DB),
    surface = Color(0xFF1E1E1E),
    onSurface = Color(0xFFECE0DB),
    surfaceVariant = Color(0xFF3A2F2B),
    onSurfaceVariant = Color(0xFFD8C2BA),
    outline = Color(0xFFA08D85),
    error = Color(0xFFFFB4AB),
    onError = Color(0xFF690005),
)

/**
 * The urgency ramp. A rescuer reads colour before words, so these are semantic and
 * deliberately outside the M3 roles: darkened for light mode, lightened for dark,
 * so the label on top keeps its contrast either way.
 */
data class UrgencyPalette(
    val critical: Color,
    val high: Color,
    val medium: Color,
    val low: Color,
    val info: Color,
) {
    /** Background for an urgency of 1..5. */
    fun forLevel(urgency: Int): Color = when (urgency) {
        5 -> critical
        4 -> high
        3 -> medium
        2 -> low
        else -> info
    }

    /** Text that sits on [forLevel]. Amber needs ink; the rest carry white. */
    fun onLevel(urgency: Int): Color = if (urgency == 3) Color(0xFF221A00) else Color.White

    fun labelFor(urgency: Int): String = when (urgency) {
        5 -> "CRITICAL"
        4 -> "HIGH"
        3 -> "MEDIUM"
        2 -> "LOW"
        else -> "INFO"
    }
}

private val LightUrgency = UrgencyPalette(
    critical = Color(0xFFB3261E),
    high = Color(0xFFD84315),
    medium = Color(0xFFF9A825),
    low = Color(0xFF558B2F),
    info = Color(0xFF616161),
)

private val DarkUrgency = UrgencyPalette(
    critical = Color(0xFFE04A3F),
    high = Color(0xFFF4703A),
    medium = Color(0xFFFFC94D),
    low = Color(0xFF8BC34A),
    info = Color(0xFF9E9E9E),
)

private val LocalUrgencyPalette = staticCompositionLocalOf { LightUrgency }

/** Urgency colours for the active theme. Read from inside composition. */
val urgencyColors: UrgencyPalette
    @Composable get() = LocalUrgencyPalette.current

@Composable
fun SankatMochanTheme(
    useDarkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {
    CompositionLocalProvider(
        LocalUrgencyPalette provides if (useDarkTheme) DarkUrgency else LightUrgency
    ) {
        MaterialTheme(
            colorScheme = if (useDarkTheme) DarkColors else LightColors,
            typography = Typography(),
            content = content
        )
    }
}
