package com.sankatmochan.mesh

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.core.content.ContextCompat
import com.sankatmochan.mesh.mesh.MeshRole
import com.sankatmochan.mesh.ui.LoraOnlyBanner
import com.sankatmochan.mesh.ui.RelayScreen
import com.sankatmochan.mesh.ui.ResponderScreen
import com.sankatmochan.mesh.ui.RoleSelectionScreen
import com.sankatmochan.mesh.ui.VictimScreen
import com.sankatmochan.mesh.ui.theme.SankatMochanTheme

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
                vm.startAsRole(role)
                // Android 12+ lets the user answer a FINE request with "Approximate", which
                // grants COARSE only and shuts GPS off. Nothing else in the app can tell
                // them, and a silent approximate grant means no coordinates in the SOS.
                if (result[Manifest.permission.ACCESS_FINE_LOCATION] != true) {
                    Toast.makeText(
                        this,
                        "Approximate location only — GPS coordinates need Precise location. " +
                            "Turn it on in Settings › Apps › Sankat-Mochan › Permissions › Location.",
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
        super.onCreate(savedInstanceState)
        setContent {
            SankatMochanTheme {
                AppRoot(vm, onPickRole = ::onPickRole)
            }
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
            vm.startAsRole(role)
        }
    }
}

@Composable
private fun AppRoot(vm: MeshViewModel, onPickRole: (MeshRole) -> Unit) {
    when (val role = vm.role) {
        null -> RoleSelectionScreen(
            nodeId = vm.nodeId,
            bluetoothReady = vm.bluetoothReady(),
            onPick = onPickRole
        )
        else -> {
            val peers by vm.peerCount.collectAsState()
            val loraOnly by vm.loraOnly.collectAsState()
            // Rendered once here so all three role screens inherit the switch.
            Surface(color = MaterialTheme.colorScheme.background) {
                Column {
                    LoraOnlyBanner(enabled = loraOnly, onChange = vm::setLoraOnly)
                    when (role) {
                        MeshRole.VICTIM -> VictimScreen(vm, peers) { vm.leaveRole() }
                        MeshRole.RESPONDER -> ResponderScreen(vm, peers) { vm.leaveRole() }
                        MeshRole.RELAY -> RelayScreen(vm, peers) { vm.leaveRole() }
                    }
                }
            }
        }
    }
}
