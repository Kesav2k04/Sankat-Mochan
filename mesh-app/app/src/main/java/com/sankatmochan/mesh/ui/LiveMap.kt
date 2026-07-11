package com.sankatmochan.mesh.ui

import android.graphics.drawable.Drawable
import android.graphics.drawable.ShapeDrawable
import android.graphics.drawable.shapes.OvalShape
import android.util.Log
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.sankatmochan.mesh.mesh.OfflineTiles
import com.sankatmochan.mesh.ui.theme.urgencyColors
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.osmdroid.tileprovider.modules.OfflineTileProvider
import org.osmdroid.tileprovider.tilesource.FileBasedTileSource
import org.osmdroid.tileprovider.util.SimpleRegisterReceiver
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker
import java.io.File

private const val TAG = "LiveMap"

/** City centre — where the map rests until the phone has its own fix. */
private val BENGALURU = GeoPoint(12.9716, 77.5946)

/**
 * A calm, expanding radar — three rings breathing outward from a steady centre dot. Drawn
 * in code (no Lottie asset, no network), it reads as "we're reaching out for you" rather
 * than a spinner that reads as "waiting". Used both as the send animation and as the
 * stand-in when no street tiles are installed yet.
 */
@Composable
fun RadarPulse(
    modifier: Modifier = Modifier,
    color: Color = urgencyColors.critical,
    rings: Int = 3,
) {
    val transition = rememberInfiniteTransition(label = "radar")
    val phase by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(2200, easing = LinearEasing), RepeatMode.Restart),
        label = "radarPhase"
    )
    val corePulse by transition.animateFloat(
        initialValue = 0.5f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(900, easing = LinearEasing), RepeatMode.Reverse),
        label = "radarCore"
    )

    Canvas(modifier) {
        val center = Offset(size.width / 2f, size.height / 2f)
        val maxR = minOf(size.width, size.height) / 2f * 0.92f
        // Each ring is offset in phase so they leave the centre in a steady procession.
        for (i in 0 until rings) {
            val p = (phase + i.toFloat() / rings) % 1f
            val radius = maxR * p
            val alpha = (1f - p).coerceIn(0f, 1f) * 0.5f
            drawCircle(color = color.copy(alpha = alpha), radius = radius, center = center)
            drawCircle(
                color = color.copy(alpha = alpha * 1.4f),
                radius = radius,
                center = center,
                style = androidx.compose.ui.graphics.drawscope.Stroke(width = 3f)
            )
        }
        // A steady, gently breathing heart at the centre — the person, holding.
        drawCircle(color = color.copy(alpha = 0.25f), radius = maxR * 0.14f * corePulse, center = center)
        drawCircle(color = color, radius = maxR * 0.06f, center = center)
    }
}

/**
 * The reassurance map: the phone's own live position resting on an offline Bengaluru
 * street map. Tiles come only from the local archive ([OfflineTiles]) — no network path
 * exists. Until an archive is installed it shows the radar with the live coordinates, so
 * the panel is always calming, never a grey void.
 */
@Composable
fun LiveLocationMap(
    meLat: Double?,
    meLng: Double?,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val archives by produceState<List<File>?>(initialValue = null) {
        value = withContext(Dispatchers.IO) { OfflineTiles.archives(context) }
    }

    val mine = MaterialTheme.colorScheme.secondary.toArgb()
    val ready = archives

    Box(modifier.background(MaterialTheme.colorScheme.surfaceContainer)) {
        if (ready.isNullOrEmpty()) {
            // No street tiles (or still unpacking): a living radar, never a blank slab.
            RadarPulse(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.primary)
            LiveCoordinateChip(meLat, meLng, Modifier.align(Alignment.BottomStart))
        } else {
            AndroidView(
                factory = { ctx ->
                    OfflineTiles.configure(ctx)
                    MapView(ctx).apply {
                        setUseDataConnection(false)
                        setMultiTouchControls(true)
                        setTilesScaledToDpi(true)
                        // Stay within the zoom levels the bundled archive actually holds, so a
                        // pinch never lands on a blank tile.
                        setMinZoomLevel(11.0)
                        setMaxZoomLevel(15.0)
                        try {
                            val provider = OfflineTileProvider(
                                SimpleRegisterReceiver(ctx), ready.toTypedArray()
                            )
                            tileProvider = provider
                            provider.archives.firstOrNull()
                                ?.tileSources?.firstOrNull()
                                ?.let { setTileSource(FileBasedTileSource.getSource(it)) }
                        } catch (e: Exception) {
                            Log.w(TAG, "offline tile provider failed: ${e.message}")
                        }
                        controller.setZoom(15.0)
                        controller.setCenter(BENGALURU)
                    }
                },
                update = { map ->
                    map.overlays.clear()
                    val here = if (meLat != null && meLng != null) GeoPoint(meLat, meLng) else BENGALURU
                    map.overlays.add(
                        Marker(map).apply {
                            position = here
                            setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_CENTER)
                            icon = dot(mine, 30)
                            title = if (meLat != null) "You are here" else "Bengaluru"
                        }
                    )
                    map.controller.animateTo(here)
                    map.invalidate()
                },
                onRelease = { it.onDetach() },
                modifier = Modifier.fillMaxSize()
            )
            // A soft top-down scrim so the map never fights the panel above it for attention.
            LiveCoordinateChip(meLat, meLng, Modifier.align(Alignment.BottomStart))
        }
    }
}

/** A small, quiet readout of the live fix, laid over the corner of the map. */
@Composable
private fun LiveCoordinateChip(meLat: Double?, meLng: Double?, modifier: Modifier = Modifier) {
    val hasFix = meLat != null && meLng != null
    Column(
        modifier
            .padding(12.dp)
            .background(
                MaterialTheme.colorScheme.surface.copy(alpha = 0.8f),
                TileShapeSmall
            )
            .padding(horizontal = 12.dp, vertical = 8.dp)
    ) {
        SectionLabel(
            if (hasFix) "your live location" else "finding your location",
            color = if (hasFix) urgencyColors.low else urgencyColors.medium
        )
        if (hasFix) {
            Text(
                "%.5f, %.5f".format(meLat, meLng),
                style = MaterialTheme.typography.bodySmall,
                fontFamily = FontFamily.Monospace,
                color = MaterialTheme.colorScheme.onSurface
            )
        }
    }
}

private fun dot(argb: Int, sizePx: Int): Drawable = ShapeDrawable(OvalShape()).apply {
    paint.color = argb
    intrinsicWidth = sizePx
    intrinsicHeight = sizePx
    setBounds(0, 0, sizePx, sizePx)
}
