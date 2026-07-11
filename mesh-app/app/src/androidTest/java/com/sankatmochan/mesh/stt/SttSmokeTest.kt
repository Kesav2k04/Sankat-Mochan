package com.sankatmochan.mesh.stt

import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * End-to-end on-device STT: run the golden hi_0 PCM through the real NPU pipeline
 * (mel → encoder QNN → ctc QNN → decode). This is the true QAIRT/context-binary check —
 * if the QNN libs or the AI-Hub context binaries don't load on this SoC, load()/transcribe()
 * fail here with the reason in logcat.
 *
 * Requires the model pushed (tools/push_stt_model.sh); skipped otherwise.
 * Run:  ./gradlew connectedDebugAndroidTest
 */
@RunWith(AndroidJUnit4::class)
class SttSmokeTest {

    @Test
    fun transcribesGoldenClipOnNpu() = runBlocking {
        val appCtx = InstrumentationRegistry.getInstrumentation().targetContext
        val testCtx = InstrumentationRegistry.getInstrumentation().context
        val engine = SttEngine(appCtx)

        assumeTrue("STT model not pushed — skipping", engine.modelsInstalled())

        val load = engine.load()
        assertTrue("load failed: $load", load is SttEngine.LoadResult.Ok)

        val pcm = readF32(testCtx, "mel_golden/pcm.f32")
        val r = engine.transcribe(pcm, null)            // null = auto-detect language
        Log.i("SttSmokeTest", "result = $r")
        assertTrue("transcribe failed", r is SttEngine.SttResult.Ok)
        r as SttEngine.SttResult.Ok
        Log.i("SttSmokeTest", "lang=${r.lang} latencyMs=${r.latencyMs} text=${r.text}")
        println("STT_SMOKE lang=${r.lang} latencyMs=${r.latencyMs} text=${r.text}")
        assertEquals("auto-LID should pick Hindi for hi_0", "hi", r.lang)
        assertTrue("empty transcript", r.text.isNotBlank())
        engine.unload()
    }

    private fun readF32(ctx: android.content.Context, asset: String): FloatArray {
        val bytes = ctx.assets.open(asset).use { it.readBytes() }
        val bb = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        return FloatArray(bytes.size / 4) { bb.float }
    }
}
