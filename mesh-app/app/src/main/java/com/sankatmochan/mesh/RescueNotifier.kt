package com.sankatmochan.mesh

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.sankatmochan.mesh.mesh.SentSos

/**
 * Turns the mesh's own "help is on the way" acknowledgement into a real system notification
 * on the victim's phone. This is not a mock: the trigger is the [SentSos] stage that
 * [com.sankatmochan.mesh.mesh.MessageStore.updateSentStatus] sets when a DELIVERED or
 * ACCEPTED envelope for this device's own SOS comes back over the mesh - so the alert only
 * ever fires on the origin phone, the moment a responder actually accepts.
 *
 * A person who has fired an SOS may well put the phone down; a banner is how they learn a
 * ranger is coming without staring at the screen.
 */
object RescueNotifier {

    private const val CHANNEL_ID = "rescue_status"

    private fun ensureChannel(context: Context) {
        val mgr = context.getSystemService(NotificationManager::class.java) ?: return
        if (mgr.getNotificationChannel(CHANNEL_ID) == null) {
            mgr.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID,
                    "Rescue status",
                    NotificationManager.IMPORTANCE_HIGH
                ).apply {
                    description = "Updates on your SOS - delivered, and help on the way."
                }
            )
        }
    }

    /**
     * Post (or replace) the status banner for one SOS. Keyed by the SOS id so a later stage
     * updates the same notification rather than stacking. Safe to call without the
     * POST_NOTIFICATIONS permission - it simply does not show.
     */
    fun notifyStatus(context: Context, sos: SentSos) {
        val (title, body) = when (sos.stage) {
            2 -> "Help is on the way" to
                "A responder is coming for you. If it's safe, stay where you are and keep your phone with you."
            1 -> "Your SOS reached the control room" to
                "Responders can see your call now. Hold on - help is being arranged."
            else -> return
        }
        ensureChannel(context)
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_rescue)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            .setAutoCancel(true)
            .build()
        try {
            NotificationManagerCompat.from(context).notify(sos.message.id.hashCode(), notification)
        } catch (_: SecurityException) {
            // POST_NOTIFICATIONS not granted (Android 13+): the in-app progress tile still shows it.
        }
    }
}
