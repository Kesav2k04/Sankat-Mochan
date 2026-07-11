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
 * Shake-to-SOS. A foreground service that watches the accelerometer and, on a deliberate hard
 * shake, raises the full-screen SOS countdown in [MainActivity].
 *
 * Why a shake and not a button combo: on the OnePlus 15 (and OxygenOS generally) the power key
 * is owned by the system — double-press is hard-wired to the camera, and multi-press is the OS's
 * own Emergency SOS — so an app can't intercept it. Volume-key triggers need an active media
 * session and are unreliable with the screen off. A shake collides with *no* OxygenOS gesture
 * (power / volume / navigation / three-finger are all untouched), works screen-on or -off while
 * this service runs, and is the established pattern for panic buttons.
 *
 * Reliability caveats (documented honestly, per CLAUDE.md #6 — this is user-safety code a human
 * must review): background Activity launch is restricted on Android 10+, so we raise the console
 * via a full-screen-intent notification (the compliant path). On Android 14+ a non-calling app's
 * full-screen intent may be shown as a heads-up notification the user taps, rather than launching
 * directly. If the OS has killed the process, the service is gone too until the app is reopened.
 */
class ShakeSosService : Service(), SensorEventListener {

    private lateinit var sensorManager: SensorManager
    private var accelerometer: Sensor? = null

    private var lastSpikeMs = 0L
    private var windowStartMs = 0L
    private var spikeCount = 0
    private var lastTriggerMs = 0L

    override fun onCreate() {
        super.onCreate()
        sensorManager = getSystemService(SENSOR_SERVICE) as SensorManager
        accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
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
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_UI)
        } ?: Log.w(TAG, "no accelerometer on this device — shake-to-SOS inactive")
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
        val gForce = sqrt((x * x + y * y + z * z).toDouble()) / SensorManager.GRAVITY_EARTH
        if (gForce < SHAKE_G) return

        val now = SystemClock.elapsedRealtime()
        // Ignore a single spike within the debounce gap (one physical jerk = one count).
        if (now - lastSpikeMs < MIN_GAP_MS) return
        lastSpikeMs = now
        // Count spikes inside a rolling window; enough of them close together = a real shake,
        // not a bump. A single knock never fires an SOS.
        if (now - windowStartMs > WINDOW_MS) {
            windowStartMs = now
            spikeCount = 0
        }
        spikeCount++
        if (spikeCount >= SPIKES_TO_TRIGGER) {
            spikeCount = 0
            trigger(now)
        }
    }

    private fun trigger(now: Long) {
        if (now - lastTriggerMs < TRIGGER_COOLDOWN_MS) return
        lastTriggerMs = now
        Log.i(TAG, "shake detected — raising SOS countdown")

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
            .setContentText("Shake detected — confirm or cancel sending an SOS")
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
            .setContentTitle("Shake-to-SOS is on")
            .setContentText("Shake your phone hard to start an emergency SOS")
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
                ONGOING_CHANNEL, "Shake-to-SOS active", NotificationManager.IMPORTANCE_LOW
            ).apply { description = "Shown while the phone is watching for an emergency shake" }
        )
        nm.createNotificationChannel(
            NotificationChannel(
                ALERT_CHANNEL, "Emergency SOS alert", NotificationManager.IMPORTANCE_HIGH
            ).apply { description = "The full-screen SOS countdown raised by a shake" }
        )
    }

    companion object {
        private const val TAG = "ShakeSosService"
        const val EXTRA_SHOW_SOS_COUNTDOWN = "show_sos_countdown"

        private const val ONGOING_CHANNEL = "shake_sos_ongoing"
        private const val ALERT_CHANNEL = "shake_sos_alert"
        private const val ONGOING_ID = 42
        private const val ALERT_ID = 43

        /** Acceleration (in g) above resting gravity that counts as a spike. ~2.7g is a firm
         *  shake — well clear of walking or setting the phone down. */
        private const val SHAKE_G = 2.7
        private const val MIN_GAP_MS = 120L
        private const val WINDOW_MS = 1_200L
        private const val SPIKES_TO_TRIGGER = 3
        private const val TRIGGER_COOLDOWN_MS = 8_000L

        fun start(context: Context) {
            ContextCompat.startForegroundService(
                context, Intent(context, ShakeSosService::class.java)
            )
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, ShakeSosService::class.java))
        }
    }
}
