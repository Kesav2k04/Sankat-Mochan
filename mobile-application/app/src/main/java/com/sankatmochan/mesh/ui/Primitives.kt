package com.sankatmochan.mesh.ui

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay

/*
 * Off-Net primitives v2 - the bento kit. Every screen is a grid of Tiles with IconBadges
 * and tracked micro-labels, so the whole app reads as one instrument panel.
 */

// ── Motion system ────────────────────────────────────────────────────────────
// Three durations and one touch spring, used everywhere. Consistent timing is what
// makes motion read as designed rather than decorative.
object Motion {
    const val Fast = 160      // colour / icon state changes
    const val Mid = 280       // layout, reveals
    const val Slow = 460      // page entrances
    val touchSpring = spring<Float>(dampingRatio = 0.55f, stiffness = Spring.StiffnessMedium)
}

val TileShape = RoundedCornerShape(24.dp)
val TileShapeSmall = RoundedCornerShape(18.dp)

/** The one surface: raised tile over the page with a single hairline. */
@Composable
fun Tile(
    modifier: Modifier = Modifier,
    shape: RoundedCornerShape = TileShape,
    container: Color = MaterialTheme.colorScheme.surfaceContainer,
    stroke: Color = MaterialTheme.colorScheme.outlineVariant,
    content: @Composable () -> Unit,
) {
    Box(
        modifier
            .clip(shape)
            .background(container)
            .border(1.dp, stroke, shape)
    ) { content() }
}

/** The reference-2 signature: an icon sitting in a soft tinted circle. */
@Composable
fun IconBadge(
    icon: ImageVector,
    tint: Color,
    modifier: Modifier = Modifier,
    size: Dp = 38.dp,
    container: Color = tint.copy(alpha = 0.16f),
) {
    Box(
        modifier
            .size(size)
            .clip(CircleShape)
            .background(container),
        contentAlignment = Alignment.Center
    ) {
        androidx.compose.material3.Icon(
            icon,
            contentDescription = null,
            tint = tint,
            modifier = Modifier.size(size * 0.55f)
        )
    }
}

/** Tracked, uppercase micro-label - the tile caption. */
@Composable
fun SectionLabel(
    text: String,
    modifier: Modifier = Modifier,
    color: Color = MaterialTheme.colorScheme.onSurfaceVariant,
) {
    Text(
        text = text.uppercase(),
        style = MaterialTheme.typography.labelSmall,
        color = color,
        modifier = modifier
    )
}

/** A status line: coloured dot + text. */
@Composable
fun StatusRow(
    dotColor: Color,
    text: String,
    modifier: Modifier = Modifier,
    textColor: Color = MaterialTheme.colorScheme.onSurfaceVariant,
) {
    Row(modifier = modifier, verticalAlignment = Alignment.CenterVertically) {
        Box(
            Modifier
                .size(8.dp)
                .clip(CircleShape)
                .background(dotColor)
        )
        Spacer(Modifier.size(10.dp))
        Text(text = text, style = MaterialTheme.typography.bodySmall, color = textColor)
    }
}

/**
 * Tap with give. Scales down on press with no ripple - the scale is the feedback, which
 * reads as a physical control rather than a wash of colour.
 */
@Composable
fun Modifier.bounceClick(
    pressedScale: Float = 0.97f,
    enabled: Boolean = true,
    onClick: () -> Unit,
): Modifier {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val scale by animateFloatAsState(
        targetValue = if (pressed && enabled) pressedScale else 1f,
        animationSpec = Motion.touchSpring,
        label = "bounce"
    )
    return this
        .graphicsLayer { scaleX = scale; scaleY = scale }
        .clickable(
            interactionSource = interaction,
            indication = null,
            enabled = enabled,
            onClick = onClick
        )
}

/** Soft coloured glow behind a shape, via the platform's coloured elevation shadow. */
fun Modifier.softGlow(
    color: Color,
    shape: Shape,
    elevation: Dp = 24.dp,
    alpha: Float = 0.55f,
): Modifier = this.then(
    Modifier.graphicsLayer {
        shadowElevation = elevation.toPx()
        this.shape = shape
        clip = false
        ambientShadowColor = color.copy(alpha = alpha)
        spotShadowColor = color.copy(alpha = alpha)
    }
)

/**
 * Staggered page entrance: fade + rise, offset by [index] * 60ms. Apply to each tile in
 * a static column so the screen assembles itself instead of popping in.
 */
@Composable
fun Modifier.entrance(index: Int): Modifier {
    var shown by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        delay(index * 60L)
        shown = true
    }
    val alpha by animateFloatAsState(
        if (shown) 1f else 0f,
        tween(Motion.Slow, easing = FastOutSlowInEasing),
        label = "entA"
    )
    val rise by animateFloatAsState(
        if (shown) 0f else 18f,
        tween(Motion.Slow, easing = FastOutSlowInEasing),
        label = "entY"
    )
    return this.graphicsLayer {
        this.alpha = alpha
        translationY = rise * density
    }
}

/**
 * The app's switch. Material's Switch carries stock M3 shapes; this one matches the
 * tile language - pill track, white thumb on a spring, red only when live.
 */
@Composable
fun GlassSwitch(
    checked: Boolean,
    onChange: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
    label: String = "toggle",
) {
    val scheme = MaterialTheme.colorScheme
    val track by animateColorAsState(
        if (checked) scheme.primary else scheme.surfaceContainerHighest,
        tween(Motion.Fast),
        label = "track"
    )
    val thumbX by animateDpAsState(
        if (checked) 23.dp else 3.dp,
        spring(dampingRatio = 0.7f, stiffness = Spring.StiffnessMediumLow),
        label = "thumb"
    )
    val interaction = remember { MutableInteractionSource() }
    Box(
        modifier
            .width(50.dp)
            .height(30.dp)
            .clip(CircleShape)
            .background(track)
            .border(1.dp, if (checked) Color.Transparent else scheme.outline, CircleShape)
            .clickable(
                interactionSource = interaction,
                indication = null
            ) { onChange(!checked) }
            .semantics { contentDescription = label }
    ) {
        Box(
            Modifier
                .align(Alignment.CenterStart)
                .offset(x = thumbX)
                .size(24.dp)
                .clip(CircleShape)
                .background(Color.White)
        )
    }
}

/**
 * The Off-Net mark, drawn in code: a red squircle carrying a broadcast glyph - one node,
 * two arcs leaving it. The same motif as the launcher icon, so the brand is one shape.
 */
@Composable
fun LogoMark(size: Dp, modifier: Modifier = Modifier) {
    val red = MaterialTheme.colorScheme.primary
    Canvas(modifier.size(size)) {
        val w = this.size.width
        drawRoundRect(
            brush = Brush.linearGradient(
                listOf(red, Color(0xFFC93840)),
                start = Offset.Zero,
                end = Offset(w, w)
            ),
            cornerRadius = CornerRadius(w * 0.3f)
        )
        val cx = w * 0.36f
        val cy = w * 0.64f
        val stroke = w * 0.075f
        // Node.
        drawCircle(Color.White, radius = w * 0.075f, center = Offset(cx, cy))
        // Two arcs, opening up-right - the signal leaving the node.
        for (r in listOf(w * 0.20f, w * 0.34f)) {
            drawArc(
                color = Color.White,
                startAngle = -90f,
                sweepAngle = 90f,
                useCenter = false,
                topLeft = Offset(cx - r, cy - r),
                size = androidx.compose.ui.geometry.Size(r * 2, r * 2),
                style = Stroke(width = stroke, cap = StrokeCap.Round)
            )
        }
    }
}

/**
 * A hand-sketched mesh: nodes joined by dashed links, one node lit red. Sits behind the
 * home headline at low alpha - the one illustrative touch, drawn in code, no asset.
 */
@Composable
fun MeshDoodle(modifier: Modifier = Modifier, alpha: Float = 1f) {
    val line = MaterialTheme.colorScheme.outline
    val red = MaterialTheme.colorScheme.primary
    Canvas(modifier) {
        val w = size.width
        val h = size.height
        val dash = PathEffect.dashPathEffect(floatArrayOf(10f, 12f))
        val nodes = listOf(
            Offset(w * 0.08f, h * 0.75f),
            Offset(w * 0.38f, h * 0.25f),
            Offset(w * 0.66f, h * 0.68f),
            Offset(w * 0.92f, h * 0.22f),
        )
        val links = listOf(0 to 1, 1 to 2, 2 to 3, 1 to 3)
        links.forEach { (a, b) ->
            drawLine(
                color = line.copy(alpha = 0.8f * alpha),
                start = nodes[a],
                end = nodes[b],
                strokeWidth = 2.5f,
                pathEffect = dash,
                cap = StrokeCap.Round
            )
        }
        nodes.forEachIndexed { i, p ->
            if (i == 0) {
                drawCircle(red.copy(alpha = alpha), radius = 9f, center = p)
                drawCircle(red.copy(alpha = 0.25f * alpha), radius = 20f, center = p)
            } else {
                drawCircle(line.copy(alpha = alpha), radius = 6f, center = p)
            }
        }
    }
}
