plugins {
    id("com.android.application") version "8.5.2"
    id("org.jetbrains.kotlin.android") version "2.0.20"
    id("org.jetbrains.kotlin.plugin.compose") version "2.0.20"
}

android {
    namespace = "com.sankatmochan.mesh"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.sankatmochan.mesh"
        minSdk = 31          // Android 12 — clean BLUETOOTH_SCAN/ADVERTISE/CONNECT permission model.
        targetSdk = 35
        versionCode = 1
        versionName = "0.1"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
    }
    androidResources {
        // The bundled Bengaluru map archive is already PNG-packed; leave it uncompressed so
        // the APK build doesn't burn time squeezing ~16 MB for no gain.
        noCompress += "mbtiles"
    }
    packaging {
        // The GenieX SDK loads its QAIRT / llama.cpp native libraries with dlopen() at
        // runtime, which needs them unpacked onto disk rather than mmap'd from the APK.
        // Legacy packaging keeps extractNativeLibs=true so the on-device LLM can start.
        jniLibs.useLegacyPackaging = true
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.09.03"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.activity:activity-compose:1.9.2")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.6")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.6")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    // Offline map rendering. Apache-2.0 (CLAUDE.md #1). Renders only from a local tile
    // archive — we never let it reach the network.
    implementation("org.osmdroid:osmdroid-android:6.1.20")

    // On-device LLM for the offline assistant. Qualcomm GenieX Android binding, published to
    // Maven Central (BSD-3-Clause per the ai-hub-apps geniex_chat_android sample it mirrors —
    // CLAUDE.md #1/#4). Runs small GGUF chat models on the Snapdragon NPU/GPU/CPU fully
    // offline; the model itself is downloaded once at runtime, not bundled in the APK.
    // Docs: https://github.com/qualcomm/ai-hub-apps/tree/main/geniex_chat_android
    implementation("com.qualcomm.qti:geniex-android:0.3.5")
    // Pulled in transitively by the GenieX SDK's data beans; declared explicitly so the
    // version is pinned. Apache-2.0.
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.3")

    debugImplementation("androidx.compose.ui:ui-tooling")
}
