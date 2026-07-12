package com.sankatmochan.mesh

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Build
import android.os.IBinder
import android.os.SystemClock
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import kotlin.math.sqrt

/**
 * Flip-to-SOS. A foreground service that watches the accelerometer's *orientation* and, on a
 * deliberate "flip the phone face-down and back up three times", raises the full-screen SOS
 * countdown in [MainActivity].
 *
 * Why a flip and not a shake or a button combo - the trade-offs we actually walked through:
 *
 *  - Shake (the previous gesture) keys on raw acceleration magnitude, so a pothole, a hard brake,
 *    a bag being set down, or a drop all spike past the threshold and fire a *false* SOS. In a
 *    moving vehicle that is a real, repeated misfire. Rejected.
 *  - Power-button multi-press can't be used: on the OnePlus 15 / OxygenOS the power key is owned
 *    by the system - a rapid multi-press is already wired to the OS's own Emergency SOS, and an
 *    app cannot intercept the key. We would be fighting (and duplicating) the platform. Rejected.
 *  - Volume-key patterns only reach an app while it is foreground or holding an active media
 *    session; screen-off they are unreliable, and mashing volume also blasts/mutes audio.
 *    Rejected as a primary trigger.
 *  - A flip keys on the *gravity vector* (which way is down), not on how hard the phone is jostled.
 *    A bump, a drop (free-fall + one impact), or walking with the phone in a pocket never produce
 *    three full, deliberate 180° inversions in a row - so the false-positive that plagued the
 *    shake gesture is designed out. It collides with no OxygenOS gesture, and it is unambiguously
 *    intentional: you have to pick the phone up and turn it over and back, three times.
 *
 * Screen-off reliability: we request the *wake-up* variant of the accelerometer where the device
 * offers one (Snapdragon sensor hub / low-power island), so orientation events keep arriving while
 * the application processor is asleep - no wake-lock, no battery drain from holding the CPU on.
 * On a device with no wake-up accelerometer we fall back to the standard one (reliable screen-on
 * and while this service is alive; the OS may batch or pause it in deep sleep).
 *
 * Safety (CLAUDE.md #6 - this is user-safety code a human must review): detecting the gesture only
 * *raises the confirmation countdown*; it never sends an SOS by itself. The SOS goes out only if
 * the 30s countdown elapses or the user taps "Send now" (see [MainActivity.sendAutoSos] and
 * [com.sankatmochan.mesh.ui.SosCountdownOverlay]). Background Activity launch is restricted on
 * Android 10+, so the countdown is raised via a full-screen-intent notification (the compliant
 * path); on Android 14+ a non-calling app's full-screen intent may show as a heads-up
 * notification the user taps rather than launching directly.
 */
class SosGestureService : Service(), SensorEventListener {

    private lateinit var sensorManager: SensorManager
    private var accelerometer: Sensor? = null

    /** Smoothed gravity Z (m/s²): +ve = screen up, -ve = screen down. Low-passed so a transient
     *  jolt can't momentarily flip the reading. */
    private var gravityZ = 0f
    private var haveGravity = false

    /** Orientation state machine: are we currently resting face-up or face-down. */
    private var orientation = FACE_UNKNOWN
    private var lastCountedOrientation = FACE_UNKNOWN

    private var windowStartMs = 0L
    private var flipCount = 0
    private var lastFlipMs = 0L
    private var lastTriggerMs = 0L

    override fun onCreate() {
        super.onCreate()
        sensorManager = getSystemService(SENSOR_SERVICE) as SensorManager
        // Prefer a wake-up accelerometer so the flip is caught with the screen off without pinning
        // the CPU awake; fall back to the standard sensor if the device has no wake-up variant.
        accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER, true)
            ?: sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        createChannels()
        // Must go foreground immediately; on API 34+ a type is mandatory.
        ServiceCompat.startForeground(
            this,
            ONGOING_ID,
            buildOngoingNotification(),
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE)
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE else 0
        )
        accelerometer?.let {
            // SENSOR_DELAY_UI (~60ms) is plenty to see an orientation change; keeps power low.
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_UI)
        } ?: Log.w(TAG, "no accelerometer on this device - flip-to-SOS inactive")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        super.onDestroy()
        runCatching { sensorManager.unregisterListener(this) }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    override fun onSensorChanged(event: SensorEvent) {
        if (event.sensor?.type != Sensor.TYPE_ACCELEROMETER) return
        val (x, y, z) = event.values

        // Only read orientation when the phone is roughly at rest under gravity. During free-fall
        // (|a| ≈ 0, i.e. a drop) or a violent jolt (|a| ≫ g) the accelerometer measures motion, not
        // "which way is down" - sampling then would let a drop or a shake masquerade as a flip.
        val magnitude = sqrt((x * x + y * y + z * z).toDouble()).toFloat()
        if (magnitude < REST_MIN || magnitude > REST_MAX) return

        // Low-pass the Z axis into a stable gravity estimate.
        gravityZ = if (!haveGravity) {
            haveGravity = true
            z
        } else {
            GRAVITY_ALPHA * gravityZ + (1 - GRAVITY_ALPHA) * z
        }

        // Resolve to a stable orientation with hysteresis (the dead band between the thresholds
        // stops a phone held near-vertical from chattering up/down).
        val newOrientation = when {
            gravityZ >= FACE_UP_Z -> FACE_UP
            gravityZ <= FACE_DOWN_Z -> FACE_DOWN
            else -> orientation // inside the dead band: keep the last stable orientation
        }
        if (newOrientation == orientation) return
        orientation = newOrientation

        val now = SystemClock.elapsedRealtime()
        // A "flip" is counted when the phone comes to rest FACE-DOWN, but only if it was last
        // counted face-up - so you must turn it over *and back* between counts. A phone left lying
        // face-down and nudged can never rack up a count.
        if (orientation == FACE_DOWN && lastCountedOrientation != FACE_DOWN) {
            if (now - lastFlipMs < MIN_GAP_MS) return   // debounce a single wobble
            lastFlipMs = now
            if (now - windowStartMs > WINDOW_MS) {
                windowStartMs = now
                flipCount = 0
            }
            flipCount++
            lastCountedOrientation = FACE_DOWN
            Log.d(TAG, "flip $flipCount/$FLIPS_TO_TRIGGER")
            if (flipCount >= FLIPS_TO_TRIGGER) {
                flipCount = 0
                lastCountedOrientation = FACE_UNKNOWN
                trigger(now)
            }
        } else if (orientation == FACE_UP) {
            // Returned face-up: re-arm so the next face-down counts.
            lastCountedOrientation = FACE_UP
        }
    }

    private fun trigger(now: Long) {
        if (now - lastTriggerMs < TRIGGER_COOLDOWN_MS) return
        lastTriggerMs = now
        Log.i(TAG, "flip gesture detected - raising SOS countdown")

        val consoleIntent = Intent(this, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            putExtra(EXTRA_SHOW_SOS_COUNTDOWN, true)
        }
        val pi = PendingIntent.getActivity(
            this, 0, consoleIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val alert = NotificationCompat.Builder(this, ALERT_CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_rescue)
            .setContentTitle("Emergency SOS")
            .setContentText("Flip gesture detected - confirm or cancel sending an SOS")
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setAutoCancel(true)
            .setFullScreenIntent(pi, true)
            .setContentIntent(pi)
            .build()
        runCatching {
            (getSystemService(NOTIFICATION_SERVICE) as NotificationManager).notify(ALERT_ID, alert)
        }
        // Best-effort direct launch: succeeds when the app is already foreground; the full-screen
        // intent above covers the background/screen-off case where a direct launch is blocked.
        runCatching { startActivity(consoleIntent) }
    }

    private fun buildOngoingNotification() =
        NotificationCompat.Builder(this, ONGOING_CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_rescue)
            .setContentTitle("Flip-to-SOS is on")
            .setContentText("Flip your phone face-down and back up 3 times to start an SOS")
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .setContentIntent(
                PendingIntent.getActivity(
                    this, 1,
                    Intent(this, MainActivity::class.java),
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                )
            )
            .build()

    private fun createChannels() {
        val nm = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        nm.createNotificationChannel(
            NotificationChannel(
                ONGOING_CHANNEL, "Flip-to-SOS active", NotificationManager.IMPORTANCE_LOW
            ).apply { description = "Shown while the phone is watching for an emergency flip gesture" }
        )
        nm.createNotificationChannel(
            NotificationChannel(
                ALERT_CHANNEL, "Emergency SOS alert", NotificationManager.IMPORTANCE_HIGH
            ).apply { description = "The full-screen SOS countdown raised by the flip gesture" }
        )
    }

    companion object {
        private const val TAG = "SosGestureService"
        const val EXTRA_SHOW_SOS_COUNTDOWN = "show_sos_countdown"

        private const val ONGOING_CHANNEL = "sos_gesture_ongoing"
        private const val ALERT_CHANNEL = "sos_gesture_alert"
        private const val ONGOING_ID = 42
        private const val ALERT_ID = 43

        // Orientation states.
        private const val FACE_UNKNOWN = 0
        private const val FACE_UP = 1
        private const val FACE_DOWN = 2

        /** Gravity-Z thresholds (m/s², g ≈ 9.81). Face-up when Z is strongly positive, face-down
         *  when strongly negative; the gap between them is a dead band so a phone held on edge
         *  doesn't flicker between states. */
        private const val FACE_UP_Z = 7.5f
        private const val FACE_DOWN_Z = -7.5f

        /** Accept an orientation sample only when total acceleration is near 1 g - i.e. the phone
         *  is resting under gravity, not in free-fall (a drop) or being violently jerked (a shake).
         *  This is what makes bumps and drops physically incapable of registering as a flip. */
        private const val REST_MIN = 6.0f
        private const val REST_MAX = 13.5f

        /** Low-pass factor for the gravity estimate (higher = smoother/slower). */
        private const val GRAVITY_ALPHA = 0.7f

        private const val MIN_GAP_MS = 250L
        /** Window to complete all the flips - generous, because a frightened or injured person is
         *  not fast or precise. */
        private const val WINDOW_MS = 6_000L
        private const val FLIPS_TO_TRIGGER = 3
        private const val TRIGGER_COOLDOWN_MS = 8_000L

        fun start(context: Context) {
            ContextCompat.startForegroundService(
                context, Intent(context, SosGestureService::class.java)
            )
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, SosGestureService::class.java))
        }
    }
}
