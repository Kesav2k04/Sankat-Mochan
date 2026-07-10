package com.sankatmochan.mesh

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
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
                AppRoot(vm, onPickRole = ::onPickRole)
            }
        }
        // No role picker anymore — the phone is a victim's SOS console the moment it opens.
        // A retained ViewModel keeps its role across configuration changes, so only ask on a
        // genuinely cold start.
        if (vm.role == null) onPickRole(MeshRole.VICTIM)
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
}

@Composable
private fun AppRoot(vm: MeshViewModel, onPickRole: (MeshRole) -> Unit) {
    // The role picker is gone: the app is the victim's SOS console by default, and the
    // settings gear swaps in the responder. Until the first role actually starts (while the
    // permission prompt is up) we still render the victim console so there is never a blank
    // frame.
    val role = vm.role ?: MeshRole.VICTIM
    var settingsOpen by remember { mutableStateOf(false) }
    val openSettings = { settingsOpen = true }

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
                        MeshRole.VICTIM -> VictimScreen(vm, peers, onOpenSettings = openSettings)
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
