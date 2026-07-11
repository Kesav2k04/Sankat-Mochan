package com.sankatmochan.mesh.ui

import android.content.Context
import android.content.res.Resources
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.drawable.BitmapDrawable
import android.graphics.drawable.Drawable
import android.graphics.drawable.GradientDrawable
import com.sankatmochan.mesh.mesh.MapPoint
import com.sankatmochan.mesh.mesh.SafePoints
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker
import org.osmdroid.views.overlay.Polygon

/*
 * Map marker kit, drawn entirely in code (no bitmap assets, no network). Crisp, ringed pins so
 * a position reads as an intentional marker rather than a blurry blob against busy OSM tiles —
 * this is the fix for the "half-cut / unclear icons on the map" report as well as the base for
 * the green safe-reunion beacons.
 */

/** A filled dot with a contrasting ring. */
fun dotMarker(fillArgb: Int, sizePx: Int, ringArgb: Int = Color.WHITE): Drawable =
    GradientDrawable().apply {
        shape = GradientDrawable.OVAL
        setColor(fillArgb)
        setStroke((sizePx * 0.16f).toInt().coerceAtLeast(2), ringArgb)
        setSize(sizePx, sizePx)
        setBounds(0, 0, sizePx, sizePx)
    }

/**
 * A "radar target" beacon for a safe reunion point: concentric green rings around a white-cored
 * dot, so a muster/assembly location reads at a glance as *the safe place to go*, distinct from
 * an SOS pin. Drawn to a bitmap so osmdroid can stamp it at the point.
 */
fun reunionMarker(res: Resources, greenArgb: Int, sizePx: Int): Drawable {
    val bmp = Bitmap.createBitmap(sizePx, sizePx, Bitmap.Config.ARGB_8888)
    val c = Canvas(bmp)
    val cx = sizePx / 2f
    val cy = sizePx / 2f
    val maxR = sizePx / 2f - 2f
    val r = Color.red(greenArgb)
    val g = Color.green(greenArgb)
    val b = Color.blue(greenArgb)
    fun green(a: Int) = Color.argb(a, r, g, b)

    // Soft halo, then two rings leaving the centre — a frozen green radar wave.
    c.drawCircle(cx, cy, maxR, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = green(46) })
    val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = sizePx * 0.05f
    }
    c.drawCircle(cx, cy, maxR * 0.92f, Paint(ring).apply { color = green(150) })
    c.drawCircle(cx, cy, maxR * 0.60f, Paint(ring).apply { color = green(215) })
    // White ring + solid green core so it stays legible on any tile.
    c.drawCircle(cx, cy, maxR * 0.34f, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE })
    c.drawCircle(cx, cy, maxR * 0.24f, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = green(255) })
    return BitmapDrawable(res, bmp).apply { setBounds(0, 0, sizePx, sizePx) }
}

/**
 * Overlay the bundled safe-reunion points (always) and general landmarks (optional) onto a map.
 * Each reunion point gets a translucent green "safe zone" circle under a radar beacon; landmarks
 * get small neutral pins. Titles/snippets are plain text (CLAUDE.md #9). Call from a map
 * `update` block after clearing/adding your own SOS/position markers.
 *
 * @param safeZoneRadiusM radius of the safe-zone ring in metres.
 */
fun MapView.addSafePoints(
    context: Context,
    greenArgb: Int,
    landmarkArgb: Int,
    showLandmarks: Boolean,
    safeZoneRadiusM: Double = 130.0,
) {
    val res = context.resources
    val r = Color.red(greenArgb)
    val g = Color.green(greenArgb)
    val b = Color.blue(greenArgb)

    SafePoints.reunions(context).forEach { p ->
        val center = GeoPoint(p.lat, p.lng)
        overlays.add(
            Polygon(this).apply {
                points = Polygon.pointsAsCircle(center, safeZoneRadiusM)
                fillPaint.color = Color.argb(40, r, g, b)
                outlinePaint.color = Color.argb(140, r, g, b)
                outlinePaint.strokeWidth = 3f
                // A safe-zone ring is decoration, not a tappable feature.
                setOnClickListener { _, _, _ -> false }
            }
        )
        overlays.add(
            Marker(this).apply {
                position = center
                setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_CENTER)
                icon = reunionMarker(res, greenArgb, 46)
                title = "Safe reunion point · ${p.name}"
                snippet = p.detail
            }
        )
    }

    if (showLandmarks) {
        SafePoints.landmarks(context).forEach { p ->
            overlays.add(
                Marker(this).apply {
                    position = GeoPoint(p.lat, p.lng)
                    setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_CENTER)
                    icon = dotMarker(landmarkArgb, 20)
                    title = p.name
                    snippet = p.detail
                }
            )
        }
    }
}

/** Convenience: does the bundled dataset actually have any reunion points? */
fun hasSafePoints(context: Context): Boolean = SafePoints.all(context).isNotEmpty()
