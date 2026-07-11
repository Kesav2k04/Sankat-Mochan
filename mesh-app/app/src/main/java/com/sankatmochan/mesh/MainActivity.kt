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
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.IntentSenderRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import com.google.android.gms.common.api.ResolvableApiException
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.LocationSettingsRequest
import com.google.android.gms.location.Priority
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutHorizontally
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
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.core.content.ContextCompat
import com.sankatmochan.mesh.mesh.MeshRole
import com.sankatmochan.mesh.ui.ChatScreen
import com.sankatmochan.mesh.ui.LoraOnlyBanner
import com.sankatmochan.mesh.ui.RelayScreen
import com.sankatmochan.mesh.ui.ResponderScreen
import com.sankatmochan.mesh.ui.RoleSettingsDialog
import com.sankatmochan.mesh.ui.SosCountdownOverlay
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

    // Location, the microphone and notifications are requested in the same prompt but are all
    // OPTIONAL — if denied, the mesh still starts and a text SOS still sends, just without
    // coordinates, a voice clip, or the "help is on the way" banner. POST_NOTIFICATIONS is a
    // runtime permission only on Android 13+.
    private val requestedPermissions = blePermissions +
        Manifest.permission.ACCESS_FINE_LOCATION +
        Manifest.permission.RECORD_AUDIO +
        (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU)
            arrayOf(Manifest.permission.POST_NOTIFICATIONS) else emptyArray())

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
                // The moment the app is usable, make sure location is actually switched on —
                // one tap, in place, no trip to Settings.
                if (role == MeshRole.VICTIM) promptEnableLocationOneTap()
                updateSosGestureService(role)
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
    // time the app is in front. Only BLUETOOTH is enforced — the mesh cannot run without it.
    // Location is deliberately NOT forced: an SOS sends fine with no coordinates, so nagging
    // the user to turn GPS on would be wrong. `suppressNextRadioCheck` stops the resume that
    // fires when we come back FROM the Bluetooth prompt from immediately firing another.
    private var suppressNextRadioCheck = false

    private val enableBtLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
            suppressNextRadioCheck = true
        }

    // Result of the one-tap "turn location on" system dialog. Whatever the user chose, re-sync
    // our own location state so the indicator reflects reality immediately.
    private val enableLocationLauncher =
        registerForActivityResult(ActivityResultContracts.StartIntentSenderForResult()) {
            vm.refreshLocation()
        }

    // React the moment a radio changes under us while we're in the foreground: chase
    // Bluetooth back on, but for location only re-sync our own state (never force it).
    private val radioStateReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            when (intent?.action) {
                BluetoothAdapter.ACTION_STATE_CHANGED -> enforceRadios()
                LocationManager.MODE_CHANGED_ACTION -> vm.refreshLocation()
            }
        }
    }

    // Light/dark is a user choice now (the map reads better in daylight against light OSM
    // tiles), persisted so it survives a restart. Compose snapshot state so a toggle recomposes
    // the whole tree; defaults to the control-room dark look.
    private val themePrefs by lazy { getSharedPreferences("offnet_prefs", Context.MODE_PRIVATE) }
    private var darkTheme by mutableStateOf(true)

    // Raised by the flip gesture (SosGestureService) — shows the full-screen 30s SOS countdown.
    private var showSosCountdown by mutableStateOf(false)

    override fun onCreate(savedInstanceState: Bundle?) {
        // targetSdk 35 on Android 15+ draws the app edge-to-edge with no automatic system-bar
        // insets. The bar icon colour must match the theme (light icons on the dark ground, dark
        // icons on the light one) or they vanish. The layouts pad for the bars via
        // safeDrawingPadding.
        darkTheme = themePrefs.getBoolean(KEY_DARK, true)
        applyBarStyle(darkTheme)
        super.onCreate(savedInstanceState)
        setContent {
            OffNetTheme(darkTheme = darkTheme) {
                Box(modifier = Modifier.fillMaxSize()) {
                    AppRoot(
                        vm,
                        onPickRole = ::onPickRole,
                        onSosSent = ::requestBatterySaver,
                        darkTheme = darkTheme,
                        onToggleTheme = ::toggleTheme,
                    )
                    // Full-screen flip-triggered countdown, drawn over everything.
                    if (showSosCountdown) {
                        SosCountdownOverlay(
                            totalSeconds = 30,
                            onSend = {
                                showSosCountdown = false
                                sendAutoSos()
                            },
                            onCancel = {
                                // "No" on the countdown means the user is safe — leave the app.
                                showSosCountdown = false
                                finish()
                            },
                        )
                    }
                }
            }
        }
        // No role picker anymore — the phone is a victim's SOS console the moment it opens.
        // A retained ViewModel keeps its role across configuration changes, so only ask on a
        // genuinely cold start.
        if (vm.role == null) onPickRole(MeshRole.VICTIM)
        handleSosGestureIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleSosGestureIntent(intent)
    }

    /** A flip gesture fired while we were backgrounded routes back here via a full-screen intent. */
    private fun handleSosGestureIntent(intent: Intent?) {
        if (intent?.getBooleanExtra(SosGestureService.EXTRA_SHOW_SOS_COUNTDOWN, false) == true) {
            showSosCountdown = true
        }
    }

    /**
     * Fire an SOS with safe emergency defaults — used when the countdown elapses or the user taps
     * "Send now". A person who triggered the flip gesture may be unable to fill in details, so this
     * sends the highest urgency with the live GPS fix the ViewModel already holds, then nudges
     * Battery saver like any other send.
     */
    private fun sendAutoSos() {
        vm.sendSos(
            category = "trapped",
            urgency = 5,
            gist = "Auto-SOS — triggered by flip gesture",
            lang = "en",
            locationHint = "",
        )
        requestBatterySaver()
    }

    private fun applyBarStyle(dark: Boolean) {
        val transparent = android.graphics.Color.TRANSPARENT
        if (dark) {
            enableEdgeToEdge(
                statusBarStyle = SystemBarStyle.dark(transparent),
                navigationBarStyle = SystemBarStyle.dark(transparent),
            )
        } else {
            enableEdgeToEdge(
                statusBarStyle = SystemBarStyle.light(transparent, transparent),
                navigationBarStyle = SystemBarStyle.light(transparent, transparent),
            )
        }
    }

    private fun toggleTheme() {
        darkTheme = !darkTheme
        themePrefs.edit().putBoolean(KEY_DARK, darkTheme).apply()
        applyBarStyle(darkTheme)
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
        // Re-sync the location indicator with reality every time we come forward — the user
        // may have toggled Location off in the shade while the app was in the background.
        vm.refreshLocation()
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
            if (role == MeshRole.VICTIM) promptEnableLocationOneTap()
            updateSosGestureService(role)
        }
    }

    /** The flip-to-SOS gesture only makes sense for the person who might need help. Run the
     *  detector while this phone is a victim console; stop it if it becomes a responder. */
    private fun updateSosGestureService(role: MeshRole) {
        if (role == MeshRole.VICTIM) SosGestureService.start(this) else SosGestureService.stop(this)
    }

    /**
     * One-tap location enable. When location is off, Play services can pop a system dialog that
     * switches it on in place — no trip to Settings (the redirect the app used to rely on). If
     * the dialog can't be shown (already on, or no GMS on this device) we do nothing: an SOS
     * still sends without a fix, so this is a nudge, never a gate.
     */
    private fun promptEnableLocationOneTap() {
        val hasLocationPermission =
            ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) ==
                PackageManager.PERMISSION_GRANTED ||
                ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) ==
                PackageManager.PERMISSION_GRANTED
        if (!hasLocationPermission) return

        val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 5_000L).build()
        val settingsRequest = LocationSettingsRequest.Builder()
            .addLocationRequest(request)
            .setAlwaysShow(true)
            .build()
        LocationServices.getSettingsClient(this)
            .checkLocationSettings(settingsRequest)
            .addOnFailureListener { e ->
                if (e is ResolvableApiException) {
                    try {
                        enableLocationLauncher.launch(
                            IntentSenderRequest.Builder(e.resolution).build()
                        )
                    } catch (_: Exception) {
                        // The pending intent was already consumed/cancelled — nothing to do.
                    }
                }
            }
    }

    // --- Radio enforcement -------------------------------------------------

    private fun bluetoothAdapter(): BluetoothAdapter? =
        (getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager)?.adapter

    private fun isBluetoothOn(): Boolean = bluetoothAdapter()?.isEnabled == true

    /**
     * Chase Bluetooth back on — and only Bluetooth. Android forbids a normal app from
     * flipping a radio on silently, so the strongest we can do is put the system enable
     * dialog in front of the user. Location is intentionally left alone: an SOS goes out with
     * or without a fix, so forcing GPS on would be the wrong kind of pushy.
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
    darkTheme: Boolean,
    onToggleTheme: () -> Unit,
) {
    // The role picker is gone: the app is the victim's SOS console by default, and the
    // settings gear swaps in the responder. Until the first role actually starts (while the
    // permission prompt is up) we still render the victim console so there is never a blank
    // frame.
    val role = vm.role ?: MeshRole.VICTIM
    var settingsOpen by remember { mutableStateOf(false) }
    // Survives rotation / process death so an auto-rotate never bounces the user back home.
    var chatOpen by rememberSaveable { mutableStateOf(false) }
    val openSettings = { settingsOpen = true }

    // Task 3: on the responder screen the back gesture returns to the user (home) console
    // rather than closing the app — "user" is the previous page now that the picker is gone.
    BackHandler(enabled = role == MeshRole.RESPONDER && !chatOpen) { onPickRole(MeshRole.VICTIM) }
    // The assistant is a page over the top of whatever role is active; back closes it first.
    BackHandler(enabled = chatOpen) { chatOpen = false }

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
                        MeshRole.VICTIM -> VictimScreen(
                            vm, peers,
                            onOpenSettings = openSettings,
                            onOpenChat = { chatOpen = true },
                            onSosSent = onSosSent,
                        )
                        MeshRole.RESPONDER -> ResponderScreen(vm, peers, onOpenSettings = openSettings)
                        MeshRole.RELAY -> RelayScreen(vm, peers, onBack = openSettings)
                    }
                }
            }
        }
    }

    // The offline AI assistant slides in over the console. It owns its own ViewModel, so its
    // model stays loaded while it is on screen and is released when it leaves.
    AnimatedVisibility(
        visible = chatOpen,
        enter = slideInHorizontally(tween(320, easing = FastOutSlowInEasing)) { it } + fadeIn(tween(220)),
        exit = slideOutHorizontally(tween(240, easing = FastOutSlowInEasing)) { it } + fadeOut(tween(160)),
    ) {
        Column(modifier = Modifier.fillMaxSize().safeDrawingPadding()) {
            ChatScreen(onBack = { chatOpen = false })
        }
    }

    if (settingsOpen) {
        RoleSettingsDialog(
            current = role,
            darkTheme = darkTheme,
            onToggleTheme = onToggleTheme,
            onSelect = {
                settingsOpen = false
                onPickRole(it)
            },
            onDismiss = { settingsOpen = false },
        )
    }
}

private const val KEY_DARK = "dark_theme"
