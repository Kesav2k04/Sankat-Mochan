package com.sankatmochan.mesh

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.location.LocationManager
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.core.content.ContextCompat
import com.sankatmochan.mesh.mesh.MeshRole
import com.sankatmochan.mesh.ui.LoraOnlyBanner
import com.sankatmochan.mesh.ui.RelayScreen
import com.sankatmochan.mesh.ui.ResponderScreen
import com.sankatmochan.mesh.ui.RoleSettingsDialog
import com.sankatmochan.mesh.ui.VictimScreen
import com.sankatmochan.mesh.ui.theme.OffNetTheme

class MainActivity : ComponentActivity() {

    private val vm: MeshViewModel by viewModels()
    private var pendingRole: MeshRole? = null

    // BLE permissions are MANDATORY — the mesh can't run without them.
    private val blePermissions = arrayOf(
        Manifest.permission.BLUETOOTH_SCAN,
        Manifest.permission.BLUETOOTH_ADVERTISE,
        Manifest.permission.BLUETOOTH_CONNECT,
    )

    // Location and the microphone are requested in the same prompt but are OPTIONAL — if
    // denied, the mesh still starts and a text SOS still sends, just without coordinates
    // or the ability to record a voice message.
    private val requestedPermissions = blePermissions +
        Manifest.permission.ACCESS_FINE_LOCATION +
        Manifest.permission.RECORD_AUDIO

    private val permissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { result ->
            val role = pendingRole
            pendingRole = null
            // Only the BLE permissions gate startup; location may be false.
            val bleGranted = blePermissions.all { result[it] == true }
            if (bleGranted && role != null) {
                vm.selectRole(role)
                // Android 12+ lets the user answer a FINE request with "Approximate", which
                // grants COARSE only and shuts GPS off. Nothing else in the app can tell
                // them, and a silent approximate grant means no coordinates in the SOS.
                if (result[Manifest.permission.ACCESS_FINE_LOCATION] != true) {
                    Toast.makeText(
                        this,
                        "Approximate location only — GPS coordinates need Precise location. " +
                            "Turn it on in Settings › Apps › Off-Net › Permissions › Location.",
                        Toast.LENGTH_LONG
                    ).show()
                }
            } else if (role != null) {
                Toast.makeText(
                    this,
                    "Bluetooth permissions are required for the mesh to work",
                    Toast.LENGTH_LONG
                ).show()
            }
            // Right after the permission answer, make sure the radios themselves are on.
            enforceRadios()
        }

    // The mesh is useless with Bluetooth or location switched off, so we chase them the whole
    // time the app is in front: on launch, on every return to the foreground, and the instant
    // either radio is toggled off underneath us. `suppressNextRadioCheck` stops the resume that
    // fires when we come back FROM one of these prompts from immediately firing another — so a
    // user who declines is nagged again next time they open the app, not trapped in a loop.
    private var suppressNextRadioCheck = false

    private val enableBtLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
            suppressNextRadioCheck = true
            // Bluetooth handled — if it's on now but location is still off, chase that next.
            if (isBluetoothOn() && !isLocationOn()) promptEnableLocation()
        }

    private val locationSettingsLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
            suppressNextRadioCheck = true
        }

    // Re-check the moment a radio flips off while we're in the foreground.
    private val radioStateReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            enforceRadios()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        // targetSdk 35 on Android 15+ draws the app edge-to-edge with no automatic
        // system-bar insets. Off-Net is always dark, so we force the transparent bars to
        // carry LIGHT icons (SystemBarStyle.dark = light foreground on dark content),
        // regardless of the phone's own light/dark setting. The layouts below pad for the
        // bars themselves via safeDrawingPadding.
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
        )
        super.onCreate(savedInstanceState)
        setContent {
            OffNetTheme {
                AppRoot(vm, onPickRole = ::onPickRole, onSosSent = ::requestBatterySaver)
            }
        }
        // No role picker anymore — the phone is a victim's SOS console the moment it opens.
        // A retained ViewModel keeps its role across configuration changes, so only ask on a
        // genuinely cold start.
        if (vm.role == null) onPickRole(MeshRole.VICTIM)
    }

    override fun onResume() {
        super.onResume()
        // Watch for a radio being switched off while we're up.
        val filter = IntentFilter().apply {
            addAction(BluetoothAdapter.ACTION_STATE_CHANGED)
            addAction(LocationManager.MODE_CHANGED_ACTION)
        }
        ContextCompat.registerReceiver(
            this, radioStateReceiver, filter, ContextCompat.RECEIVER_NOT_EXPORTED
        )
        if (suppressNextRadioCheck) {
            suppressNextRadioCheck = false
        } else {
            enforceRadios()
        }
    }

    override fun onPause() {
        super.onPause()
        try {
            unregisterReceiver(radioStateReceiver)
        } catch (_: IllegalArgumentException) {
            // Never registered (e.g. paused before the first resume) — nothing to undo.
        }
    }

    private fun onPickRole(role: MeshRole) {
        val missing = requestedPermissions.any {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing) {
            pendingRole = role
            permissionLauncher.launch(requestedPermissions)
        } else {
            vm.selectRole(role)
        }
    }

    // --- Radio enforcement -------------------------------------------------

    private fun bluetoothAdapter(): BluetoothAdapter? =
        (getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager)?.adapter

    private fun isBluetoothOn(): Boolean = bluetoothAdapter()?.isEnabled == true

    private fun isLocationOn(): Boolean =
        (getSystemService(Context.LOCATION_SERVICE) as? LocationManager)?.isLocationEnabled == true

    /**
     * Chase Bluetooth first, then location — one system prompt at a time. Android forbids a
     * normal app from flipping either radio on silently, so the strongest we can do is put the
     * enable dialog (Bluetooth) or the settings screen (location) in front of the user.
     */
    private fun enforceRadios() {
        // ACTION_REQUEST_ENABLE needs BLUETOOTH_CONNECT, and while that permission is still
        // pending the permission dialog owns the screen — so hold off entirely until it's
        // granted, rather than stacking a radio prompt on top of it.
        val btPermission = ContextCompat.checkSelfPermission(
            this, Manifest.permission.BLUETOOTH_CONNECT
        ) == PackageManager.PERMISSION_GRANTED
        if (!btPermission) return

        if (bluetoothAdapter() != null && !isBluetoothOn()) {
            promptEnableBluetooth()
            return
        }
        if (!isLocationOn()) {
            promptEnableLocation()
        }
    }

    private fun promptEnableBluetooth() {
        try {
            enableBtLauncher.launch(Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE))
        } catch (_: SecurityException) {
            // BLUETOOTH_CONNECT was revoked between the check and the launch — the permission
            // flow will pick it up on the next pass.
        }
    }

    private fun promptEnableLocation() {
        Toast.makeText(
            this,
            "Turn on Location so your SOS carries your coordinates",
            Toast.LENGTH_LONG
        ).show()
        try {
            locationSettingsLauncher.launch(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS))
        } catch (_: Exception) {
            suppressNextRadioCheck = true // no settings screen to resolve to; don't loop
        }
    }

    /**
     * Fired the moment an SOS goes out. Android won't let an app turn Battery saver on itself,
     * so we drop the user straight onto the Battery-saver screen to flip it — unless it's
     * already on, in which case we stay out of the way.
     */
    private fun requestBatterySaver() {
        val pm = getSystemService(Context.POWER_SERVICE) as? PowerManager
        if (pm?.isPowerSaveMode == true) return
        Toast.makeText(
            this,
            "Turn on Battery saver to make your phone last on the mesh",
            Toast.LENGTH_LONG
        ).show()
        try {
            startActivity(Intent(Settings.ACTION_BATTERY_SAVER_SETTINGS))
        } catch (_: Exception) {
            try {
                startActivity(Intent(Settings.ACTION_SETTINGS))
            } catch (_: Exception) {
                // No settings activity to resolve to — nothing more we can do.
            }
        }
    }
}

@Composable
private fun AppRoot(
    vm: MeshViewModel,
    onPickRole: (MeshRole) -> Unit,
    onSosSent: () -> Unit,
) {
    // The role picker is gone: the app is the victim's SOS console by default, and the
    // settings gear swaps in the responder. Until the first role actually starts (while the
    // permission prompt is up) we still render the victim console so there is never a blank
    // frame.
    val role = vm.role ?: MeshRole.VICTIM
    var settingsOpen by remember { mutableStateOf(false) }
    val openSettings = { settingsOpen = true }

    // Task 3: on the responder screen the back gesture returns to the user (home) console
    // rather than closing the app — "user" is the previous page now that the picker is gone.
    BackHandler(enabled = role == MeshRole.RESPONDER) { onPickRole(MeshRole.VICTIM) }

    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        // One animated container: switching role cross-fades and rises the whole page, so the
        // app moves like one surface instead of screens popping.
        AnimatedContent(
            targetState = role,
            transitionSpec = {
                (fadeIn(tween(280, delayMillis = 60)) +
                    slideInVertically(tween(380, delayMillis = 60, easing = FastOutSlowInEasing)) { it / 18 })
                    .togetherWith(fadeOut(tween(140)))
            },
            label = "role"
        ) { current ->
            val peers by vm.peerCount.collectAsState()
            val loraOnly by vm.loraOnly.collectAsState()
            // safeDrawingPadding keeps the content clear of the status bar, the navigation
            // bar, and the keyboard, and consumes those insets so the child top bars don't
            // pad for the status bar a second time.
            Column(modifier = Modifier.fillMaxSize().safeDrawingPadding()) {
                LoraOnlyBanner(enabled = loraOnly, onChange = vm::setLoraOnly)
                Box(modifier = Modifier.weight(1f)) {
                    when (current) {
                        MeshRole.VICTIM -> VictimScreen(vm, peers, onOpenSettings = openSettings, onSosSent = onSosSent)
                        MeshRole.RESPONDER -> ResponderScreen(vm, peers, onOpenSettings = openSettings)
                        MeshRole.RELAY -> RelayScreen(vm, peers, onBack = openSettings)
                    }
                }
            }
        }
    }

    if (settingsOpen) {
        RoleSettingsDialog(
            current = role,
            onSelect = {
                settingsOpen = false
                onPickRole(it)
            },
            onDismiss = { settingsOpen = false },
        )
    }
}
