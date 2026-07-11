package com.sankatmochan.mesh.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/*
 * Off-Net design language v2 — "control room".
 *
 * One near-black neutral ground, one signal red, and a small set of state colours
 * (green = safe, amber = pending, blue = you). Everything else is greys. The discipline
 * is the aesthetic: when the only saturated thing on screen is the SOS surface, a person
 * in a panic finds it without reading anything.
 */

// ── Signal ──────────────────────────────────────────────────────────────────
internal val Signal = Color(0xFFE8484D)      // the red — SOS, critical, recording
internal val SignalHot = Color(0xFFFF6257)   // gradient tail
internal val Safe = Color(0xFF2ED48A)        // connected · locked · accepted
internal val Amber = Color(0xFFF5B03E)       // pending · searching
internal val Sky = Color(0xFF5B9DF5)         // "you" / responder

// ── Neutral ground ──────────────────────────────────────────────────────────
private val Bg = Color(0xFF0B0C0E)
private val Tile1 = Color(0xFF141519)        // resting tile
private val Tile2 = Color(0xFF191B20)        // raised tile
private val Tile3 = Color(0xFF22242B)        // interactive fills / tracks
private val Hairline = Color(0xFF23262D)
private val TextHi = Color(0xFFF4F5F7)
private val TextLo = Color(0xFF8F96A3)

private val OffNetColors = darkColorScheme(
    primary = Signal,
    onPrimary = Color.White,
    primaryContainer = Color(0xFF35171A),
    onPrimaryContainer = Color(0xFFFFD9D8),
    secondary = Sky,
    onSecondary = Color(0xFF04223C),
    secondaryContainer = Color(0xFF14304D),
    onSecondaryContainer = Color(0xFFD3E5FA),
    tertiary = Safe,
    onTertiary = Color(0xFF003825),
    background = Bg,
    onBackground = TextHi,
    surface = Bg,
    onSurface = TextHi,
    surfaceVariant = Tile2,
    onSurfaceVariant = TextLo,
    outline = Color(0xFF2E323B),
    outlineVariant = Hairline,
    error = Color(0xFFFF6B70),
    onError = Color.White,
    errorContainer = Color(0xFF35171A),
    onErrorContainer = Color(0xFFFFD9D8),
    scrim = Color(0xE6060709),
    surfaceBright = Tile3,
    surfaceDim = Bg,
    surfaceContainerLowest = Color(0xFF08090B),
    surfaceContainerLow = Tile1,
    surfaceContainer = Tile1,
    surfaceContainerHigh = Tile2,
    surfaceContainerHighest = Tile3,
)

// ── Light ground ──────────────────────────────────────────────────────────────
// A daylight companion to the dark control-room scheme, added so the offline map (light
// OSM tiles) reads with high contrast against the chrome instead of fighting a near-black
// ground. Same signal red and state colours; only the neutrals invert. The saturated SOS
// surfaces keep white ink in both modes, so nothing on the hero path changes meaning.
private val BgL = Color(0xFFF5F6F9)
private val Tile1L = Color(0xFFFFFFFF)
private val Tile2L = Color(0xFFF0F2F5)
private val Tile3L = Color(0xFFE6E9EF)
private val HairlineL = Color(0xFFDCE0E7)
private val TextHiL = Color(0xFF14171C)
private val TextLoL = Color(0xFF5A616E)

private val OffNetColorsLight = lightColorScheme(
    primary = Signal,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFFFDBDA),
    onPrimaryContainer = Color(0xFF410004),
    secondary = Color(0xFF2F6FD0),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFD6E4FA),
    onSecondaryContainer = Color(0xFF06264A),
    tertiary = Color(0xFF12A06A),
    onTertiary = Color.White,
    background = BgL,
    onBackground = TextHiL,
    surface = BgL,
    onSurface = TextHiL,
    surfaceVariant = Tile2L,
    onSurfaceVariant = TextLoL,
    outline = Color(0xFFC4C9D2),
    outlineVariant = HairlineL,
    error = Color(0xFFC0353A),
    onError = Color.White,
    errorContainer = Color(0xFFFFDBDA),
    onErrorContainer = Color(0xFF410004),
    scrim = Color(0x99202226),
    surfaceBright = Tile1L,
    surfaceDim = Tile3L,
    surfaceContainerLowest = Color.White,
    surfaceContainerLow = Tile1L,
    surfaceContainer = Tile1L,
    surfaceContainerHigh = Tile2L,
    surfaceContainerHighest = Tile3L,
)

/**
 * The urgency ramp. A rescuer reads colour before words, so these are semantic and
 * deliberately outside the M3 roles — saturated enough to separate at a glance on the
 * dark ground, never neon.
 */
data class UrgencyPalette(
    val critical: Color,
    val high: Color,
    val medium: Color,
    val low: Color,
    val info: Color,
) {
    fun forLevel(urgency: Int): Color = when (urgency) {
        5 -> critical
        4 -> high
        3 -> medium
        2 -> low
        else -> info
    }

    /** Text that sits on [forLevel]. Amber needs ink; the rest carry white. */
    fun onLevel(urgency: Int): Color = if (urgency == 3) Color(0xFF241A00) else Color.White

    fun labelFor(urgency: Int): String = when (urgency) {
        5 -> "CRITICAL"
        4 -> "HIGH"
        3 -> "MEDIUM"
        2 -> "LOW"
        else -> "INFO"
    }
}

private val OffNetUrgency = UrgencyPalette(
    critical = Signal,
    high = Color(0xFFF97850),
    medium = Amber,
    low = Safe,
    info = Color(0xFF7C8493),
)

/**
 * Brand gradients, read from inside composition. Kept here so every hero surface pulls
 * the same red instead of each screen inventing its own.
 */
data class BrandGradients(
    val sos: Brush,
    val sosPressed: Brush,
    val safe: Brush,
    val page: Brush,
) {
    val sosGlow: Color = Signal
}

private val OffNetGradients = BrandGradients(
    sos = Brush.linearGradient(listOf(Color(0xFFF2545B), Color(0xFFE23B44))),
    sosPressed = Brush.linearGradient(listOf(Color(0xFFD7434B), Color(0xFFC22F38))),
    safe = Brush.linearGradient(listOf(Color(0xFF2FC98A), Color(0xFF23B77A))),
    page = Brush.verticalGradient(listOf(Color(0xFF0D0F12), Bg)),
)

// The hero SOS/safe gradients are identical in light mode (they carry white ink either way);
// only the page wash flips to a daylight tint.
private val OffNetGradientsLight = OffNetGradients.copy(
    page = Brush.verticalGradient(listOf(Color(0xFFFFFFFF), BgL)),
)

private val LocalUrgencyPalette = staticCompositionLocalOf { OffNetUrgency }
private val LocalBrandGradients = staticCompositionLocalOf { OffNetGradients }

val urgencyColors: UrgencyPalette
    @Composable get() = LocalUrgencyPalette.current

val brandGradients: BrandGradients
    @Composable get() = LocalBrandGradients.current

// Editorial ramp: heavy, tight display for the few headline moments; wide-tracked
// micro-labels for tile captions; calm body. Platform font — nothing to ship.
private val OffNetTypography = Typography().run {
    copy(
        displayMedium = displayMedium.copy(fontWeight = FontWeight.Black, letterSpacing = (-1).sp, lineHeight = 52.sp),
        displaySmall = displaySmall.copy(fontWeight = FontWeight.Black, letterSpacing = (-0.8).sp, lineHeight = 42.sp),
        headlineLarge = headlineLarge.copy(fontWeight = FontWeight.Black, letterSpacing = (-0.6).sp),
        headlineMedium = headlineMedium.copy(fontWeight = FontWeight.Bold, letterSpacing = (-0.4).sp),
        headlineSmall = headlineSmall.copy(fontWeight = FontWeight.Bold, letterSpacing = (-0.2).sp),
        titleLarge = titleLarge.copy(fontWeight = FontWeight.Bold, letterSpacing = (-0.2).sp),
        titleMedium = titleMedium.copy(fontWeight = FontWeight.Bold),
        labelMedium = labelMedium.copy(letterSpacing = 1.2.sp, fontWeight = FontWeight.Bold),
        labelSmall = labelSmall.copy(letterSpacing = 1.4.sp, fontWeight = FontWeight.SemiBold),
    )
}

@Composable
fun OffNetTheme(
    darkTheme: Boolean = true,
    content: @Composable () -> Unit
) {
    // The urgency ramp stays identical in both modes — a rescuer must read "critical red" the
    // same way in daylight and at night. Only the neutral chrome and page wash switch.
    CompositionLocalProvider(
        LocalUrgencyPalette provides OffNetUrgency,
        LocalBrandGradients provides if (darkTheme) OffNetGradients else OffNetGradientsLight,
    ) {
        MaterialTheme(
            colorScheme = if (darkTheme) OffNetColors else OffNetColorsLight,
            typography = OffNetTypography,
            content = content
        )
    }
}
