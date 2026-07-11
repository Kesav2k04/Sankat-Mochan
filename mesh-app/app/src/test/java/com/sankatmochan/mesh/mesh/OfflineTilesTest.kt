package com.sankatmochan.mesh.mesh

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Guards the fix for the "half-rendered / blank grey map" bug: every MapView that reads the
 * bundled archive clamps its zoom to [OfflineTiles.MIN_ZOOM]..[OfflineTiles.MAX_ZOOM], so a
 * pinch or a lone-pin `setZoom(17.0)` can never ask for a tile deeper than the archive holds.
 */
class OfflineTilesTest {

    @Test
    fun clampZoom_keepsInRangeValuesUntouched() {
        assertEquals(11.0, OfflineTiles.clampZoom(11.0), 0.0)
        assertEquals(13.0, OfflineTiles.clampZoom(13.0), 0.0)
        assertEquals(15.0, OfflineTiles.clampZoom(15.0), 0.0)
    }

    @Test
    fun clampZoom_capsAboveMax() {
        // The concrete regression: a single-victim map used setZoom(17.0) with a z15 archive.
        assertEquals(OfflineTiles.MAX_ZOOM, OfflineTiles.clampZoom(17.0), 0.0)
        assertEquals(OfflineTiles.MAX_ZOOM, OfflineTiles.clampZoom(21.0), 0.0)
    }

    @Test
    fun clampZoom_raisesBelowMin() {
        assertEquals(OfflineTiles.MIN_ZOOM, OfflineTiles.clampZoom(3.0), 0.0)
        assertEquals(OfflineTiles.MIN_ZOOM, OfflineTiles.clampZoom(0.0), 0.0)
    }

    @Test
    fun zoomBand_isSaneAndMatchesArchive() {
        assertTrue("min must be below max", OfflineTiles.MIN_ZOOM < OfflineTiles.MAX_ZOOM)
        // These constants MUST track tools/fetch_bengaluru_tiles.py (--minzoom 11 --maxzoom 15)
        // and the mbtiles metadata; if the archive is rebuilt at a new depth, update both.
        assertEquals(11.0, OfflineTiles.MIN_ZOOM, 0.0)
        assertEquals(15.0, OfflineTiles.MAX_ZOOM, 0.0)
    }
}
