package com.sankatmochan.mesh.ui

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * Pure-math coverage for the rescuer's bearing/distance readout. The framework-backed
 * [Geo.distanceMeters]/[Geo.bearingDegrees] need a device (android.location.Location), but the
 * two functions a person actually reads - the compass point and the distance string - are
 * pure Kotlin and unit-testable here.
 */
class GeoTest {

    @Test
    fun compassPoint_mapsCardinalsAndWraps() {
        assertEquals("N", Geo.compassPoint(0f))
        assertEquals("E", Geo.compassPoint(90f))
        assertEquals("S", Geo.compassPoint(180f))
        assertEquals("W", Geo.compassPoint(270f))
        // 360 must wrap back to N, not index out of the 16-point table.
        assertEquals("N", Geo.compassPoint(360f))
        assertEquals("NE", Geo.compassPoint(45f))
    }

    @Test
    fun compassPoint_roundsToNearestOfSixteen() {
        assertEquals("NNE", Geo.compassPoint(22.5f))
        assertEquals("N", Geo.compassPoint(11f))   // rounds down to N
        assertEquals("NNE", Geo.compassPoint(12f))  // rounds up to NNE
    }

    @Test
    fun formatDistance_metresBelowAKilometre() {
        assertEquals("0 m", Geo.formatDistance(0f))
        assertEquals("420 m", Geo.formatDistance(420f))
        assertEquals("999 m", Geo.formatDistance(999f))
    }

    @Test
    fun formatDistance_kilometresAtAndAboveAThousand() {
        assertEquals("1.0 km", Geo.formatDistance(1000f))
        assertEquals("1.4 km", Geo.formatDistance(1400f))
        assertEquals("12.3 km", Geo.formatDistance(12345f))
    }
}
