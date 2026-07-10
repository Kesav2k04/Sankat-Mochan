package com.sankatmochan.mesh.mesh

import android.content.Context
import android.util.Log
import org.osmdroid.config.Configuration
import java.io.File

/**
 * Finds the map tiles this phone can draw from, with no network involved.
 *
 * osmdroid renders from a local archive — an .mbtiles / .sqlite / .zip / .gemf file
 * generated ahead of time for the operating region. Two places are searched, in order:
 *
 *  1. `assets/tiles/` inside the APK, copied once into app-private storage. Ship the
 *     archive here and every install carries the map.
 *  2. Whatever is already sitting in that same private directory, so a large archive
 *     can be pushed after install without rebuilding:
 *
 *        adb push region.mbtiles /sdcard/Android/data/com.sankatmochan.mesh/files/osmdroid/tiles/
 *
 * Everything lives under `filesDir`, which needs no storage permission on API 31+.
 * If nothing is found the responder screen falls back to bearing-and-distance, which
 * needs no map data at all — a blank grey map would be worse than no map.
 */
object OfflineTiles {

    private const val ASSET_DIR = "tiles"
    private val SUPPORTED = setOf("mbtiles", "sqlite", "zip", "gemf")

    /** osmdroid insists on being told where to live before a MapView is inflated. */
    fun configure(context: Context) {
        val cfg = Configuration.getInstance()
        // Deliberately NOT androidx.preference — that would pull in another dependency
        // for a handful of keys osmdroid only writes.
        cfg.load(context, context.getSharedPreferences("osmdroid", Context.MODE_PRIVATE))
        cfg.userAgentValue = context.packageName
        cfg.osmdroidBasePath = basePath(context)
        cfg.osmdroidTileCache = tileDir(context)
    }

    private fun basePath(context: Context) = File(context.filesDir, "osmdroid").apply { mkdirs() }
    private fun tileDir(context: Context) = File(basePath(context), "tiles").apply { mkdirs() }

    /**
     * Copy any bundled archives out of assets (once), then list everything usable.
     * Returns an empty list when this build ships no map — that is a supported state.
     */
    fun archives(context: Context): List<File> {
        val dest = tileDir(context)
        val bundled = try {
            context.assets.list(ASSET_DIR).orEmpty()
        } catch (e: Exception) {
            emptyArray<String>()
        }
        for (name in bundled) {
            if (name.substringAfterLast('.', "").lowercase() !in SUPPORTED) continue
            val out = File(dest, name)
            if (out.isFile && out.length() > 0L) continue          // already unpacked
            try {
                context.assets.open("$ASSET_DIR/$name").use { input ->
                    out.outputStream().use { input.copyTo(it) }
                }
                Log.i(TAG, "unpacked bundled map archive $name (${out.length()} bytes)")
            } catch (e: Exception) {
                Log.w(TAG, "could not unpack $name: ${e.message}")
                out.delete()   // never leave a truncated archive behind
            }
        }
        return dest.listFiles()
            ?.filter { it.isFile && it.length() > 0L && it.extension.lowercase() in SUPPORTED }
            ?.sortedBy { it.name }
            .orEmpty()
    }

    private const val TAG = "OfflineTiles"
}
