package com.sankatmochan.mesh.ui

import android.content.Context
import android.util.Log
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.sankatmochan.mesh.mesh.OfflineTiles
import com.sankatmochan.mesh.model.SosMessage
import com.sankatmochan.mesh.ui.theme.urgencyColors
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.osmdroid.views.CustomZoomButtonsController
import org.osmdroid.tileprovider.modules.OfflineTileProvider
import org.osmdroid.tileprovider.tilesource.FileBasedTileSource
import org.osmdroid.tileprovider.util.SimpleRegisterReceiver
import org.osmdroid.util.BoundingBox
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker
import java.io.File

private const val TAG = "OfflineMap"

/**
 * The victims, pinned on a map drawn entirely from a local tile archive.
 *
 * Offline recipe follows the osmdroid project's own documented OfflineTileProvider
 * usage (github.com/osmdroid/osmdroid, Apache-2.0). Two things keep it truly offline:
 * an [OfflineTileProvider] that only ever reads the archive, and `setUseDataConnection(false)`
 * so a missing tile renders blank instead of triggering a fetch.
 *
 * When no archive is installed this degrades to [NoMapNote] rather than a grey void.
 */
@Composable
fun OfflineMapCard(
    victims: List<SosMessage>,
    meLat: Double?,
    meLng: Double?,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val pins = victims.filter { it.hasLocation }

    // Unpacking a bundled archive is heavy file IO - a hundred megabytes is normal for
    // a city at street zoom. Never on the main thread, or the first launch is an ANR.
    val archives by produceState<List<File>?>(initialValue = null) {
        value = withContext(Dispatchers.IO) { OfflineTiles.archives(context) }
    }

    when {
        archives == null -> {
            LoadingMapNote(modifier)
            return
        }
        archives!!.isEmpty() -> {
            NoMapNote(pins.size, modifier)
            return
        }
    }
    val ready = archives!!
    if (pins.isEmpty() && (meLat == null || meLng == null)) {
        // Nothing to centre on; a map of nowhere helps no one.
        return
    }

    val critical = urgencyColors.critical.toArgb()
    val mine = MaterialTheme.colorScheme.secondary.toArgb()
    val safeArgb = urgencyColors.low.toArgb()
    val landmarkArgb = MaterialTheme.colorScheme.onSurfaceVariant.toArgb()

    var mapRef by remember { mutableStateOf<MapView?>(null) }
    val focus = when {
        meLat != null && meLng != null -> GeoPoint(meLat, meLng)
        pins.isNotEmpty() -> GeoPoint(pins.first().lat!!, pins.first().lng!!)
        else -> null
    }

    Tile(modifier.fillMaxWidth()) {
        Box(
            Modifier
                .fillMaxWidth()
                .height(300.dp)
                .clip(TileShape)
        ) {
            AndroidView(
                factory = { ctx ->
                    OfflineTiles.configure(ctx)
                    MapView(ctx).apply {
                        // No network path exists at all: the provider reads the archive only.
                        setUseDataConnection(false)
                        setMultiTouchControls(true)
                        setTilesScaledToDpi(true)
                        isHorizontalMapRepetitionEnabled = false
                        isVerticalMapRepetitionEnabled = false
                        // Stay inside the zoom levels the bundled archive actually holds, so a
                        // pinch (or the fit-to-bounds below) never lands on a blank grey tile.
                        setMinZoomLevel(OfflineTiles.MIN_ZOOM)
                        setMaxZoomLevel(OfflineTiles.MAX_ZOOM)
                        // Hide osmdroid's stock grey +/- buttons; custom controls replace them.
                        zoomController.setVisibility(CustomZoomButtonsController.Visibility.NEVER)
                        try {
                            val provider = OfflineTileProvider(
                                SimpleRegisterReceiver(ctx), ready.toTypedArray()
                            )
                            tileProvider = provider
                            val sourceName = provider.archives
                                .firstOrNull()
                                ?.tileSources
                                ?.firstOrNull()
                            if (sourceName != null) {
                                setTileSource(FileBasedTileSource.getSource(sourceName))
                            }
                        } catch (e: Exception) {
                            // A corrupt archive must not take the rescuer's screen down.
                            Log.w(TAG, "offline tile provider failed: ${e.message}")
                        }
                        mapRef = this
                    }
                },
                update = { map ->
                    drawPins(map, context, pins, meLat, meLng, critical, mine, safeArgb, landmarkArgb)
                },
                onRelease = { map -> map.onDetach() },
                modifier = Modifier.fillMaxWidth().height(300.dp)
            )
            MapControls(
                modifier = Modifier.align(Alignment.BottomEnd),
                onRecenter = { focus?.let { mapRef?.controller?.animateTo(it) } },
                onZoomIn = { mapRef?.controller?.zoomIn() },
                onZoomOut = { mapRef?.controller?.zoomOut() },
            )
        }
    }
}

private fun drawPins(
    map: MapView,
    context: Context,
    pins: List<SosMessage>,
    meLat: Double?,
    meLng: Double?,
    criticalArgb: Int,
    mineArgb: Int,
    safeArgb: Int,
    landmarkArgb: Int,
) {
    map.overlays.clear()
    // Safe reunion points + landmarks under the incident pins, so an SOS is never hidden by a
    // safe-zone ring. The auto-zoom below only fits SOS/you, keeping focus on the incident.
    map.addSafePoints(
        context = context,
        greenArgb = safeArgb,
        landmarkArgb = landmarkArgb,
        showLandmarks = true,
    )
    val points = mutableListOf<GeoPoint>()

    for (sos in pins) {
        val p = GeoPoint(sos.lat!!, sos.lng!!)
        points += p
        map.overlays.add(
            Marker(map).apply {
                position = p
                setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_CENTER)
                icon = dotMarker(criticalArgb, 34)
                // Untrusted incoming text, shown as a plain title (CLAUDE.md #9).
                title = "${sos.origin} · ${sos.category.ifBlank { "SOS" }}"
                snippet = "%.6f, %.6f".format(sos.lat, sos.lng)
            }
        )
    }

    if (meLat != null && meLng != null) {
        val me = GeoPoint(meLat, meLng)
        points += me
        map.overlays.add(
            Marker(map).apply {
                position = me
                setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_CENTER)
                icon = dotMarker(mineArgb, 26)
                title = "You"
            }
        )
    }

    if (points.isEmpty()) return

    if (points.size == 1) {
        // Closest the archive can draw - 17 would sit two levels above the deepest tile and
        // render blank grey. clampZoom keeps a lone pin as tight as the tiles allow.
        map.controller.setZoom(OfflineTiles.clampZoom(17.0))
        map.controller.setCenter(points[0])
    } else {
        // zoomToBoundingBox needs a laid-out view, so defer until we have one. The fit zoom it
        // computes can land above the archive's deepest tile (blank grey), so clamp it back into
        // the stored band afterwards.
        val box = BoundingBox.fromGeoPoints(points).increaseByScale(1.4f)
        val fit = {
            map.zoomToBoundingBox(box, false)
            map.controller.setZoom(OfflineTiles.clampZoom(map.zoomLevelDouble))
        }
        map.addOnFirstLayoutListener { _, _, _, _, _ -> fit() }
        if (map.width > 0 && map.height > 0) fit()
    }
    map.invalidate()
}

/** First launch, while a bundled archive is unpacked out of the APK. */
@Composable
private fun LoadingMapNote(modifier: Modifier = Modifier) {
    Tile(modifier.fillMaxWidth()) {
        Text(
            "Preparing the offline map…",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(16.dp)
        )
    }
}

/**
 * Shown when the build carries no tile archive. Says exactly what is missing and how
 * to supply it, because "no map" is a deployment state, not a crash.
 */
@Composable
private fun NoMapNote(pinCount: Int, modifier: Modifier = Modifier) {
    Tile(modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Text(
                "No offline map installed",
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onSurface
            )
            Spacer(Modifier.height(4.dp))
            Text(
                "Coordinates, distance and bearing below still work. To draw a map, put an " +
                    ".mbtiles archive for your region in the app's tiles folder and restart.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            if (pinCount > 0) {
                Spacer(Modifier.height(6.dp))
                Text(
                    "$pinCount call${if (pinCount == 1) "" else "s"} carrying GPS coordinates",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}
