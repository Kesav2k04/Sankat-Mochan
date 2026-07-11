import java.util.Properties

plugins {
    id("com.android.application") version "8.5.2"
    id("org.jetbrains.kotlin.android") version "2.0.20"
    id("org.jetbrains.kotlin.plugin.compose") version "2.0.20"
}

// Hugging Face token for gated model pulls (Gemma). Read from the gitignored local.properties
// so the secret never lands in version control (CLAUDE.md #2). Absent locally → empty string,
// and only gated models fail to download (non-gated ones still work).
val huggingFaceToken: String = run {
    val props = Properties()
    val f = rootProject.file("local.properties")
    if (f.exists()) f.inputStream().use { props.load(it) }
    props.getProperty("HF_TOKEN").orEmpty()
}

android {
    namespace = "com.sankatmochan.mesh"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.sankatmochan.mesh"
        minSdk = 31          // Android 12 - clean BLUETOOTH_SCAN/ADVERTISE/CONNECT permission model.
        targetSdk = 35
        versionCode = 1
        versionName = "0.1"

        // Injected from local.properties at build time - never a committed literal.
        buildConfigField("String", "HF_TOKEN", "\"$huggingFaceToken\"")

        ndk {
            // Every Snapdragon device we target (incl. the OnePlus 15 demo phone) is arm64.
            // GenieX ships native libs for several ABIs; keeping only arm64-v8a roughly
            // halves the APK.
            abiFilters += "arm64-v8a"
        }
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
        buildConfig = true
    }
    testOptions {
        unitTests {
            // Let framework calls the code under test makes for real (org.json) resolve to the
            // Apache-2.0 android-json dependency below, and make the remaining android.jar stubs
            // (android.util.Log) no-op returning defaults instead of throwing "Stub!". This keeps
            // the unit tests hermetic and fast - no device, no emulator, no Robolectric runtime
            // download.
            isReturnDefaultValues = true
        }
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
    // archive - we never let it reach the network.
    implementation("org.osmdroid:osmdroid-android:6.1.20")

    // LICENSE FLAG (CLAUDE.md #1): Google Play services is NOT OSI open-source - it ships under
    // the proprietary Google APIs Terms of Service. It's included ONLY for the one-tap "turn on
    // GPS" system dialog (SettingsClient) so we can enable location without kicking the user out
    // to Settings. No location data leaves the device through it. A human should confirm this
    // dependency is acceptable before shipping; the app otherwise uses the framework
    // LocationManager and needs no GMS.
    implementation("com.google.android.gms:play-services-location:21.3.0")

    // On-device LLM for the offline assistant. Qualcomm GenieX Android binding, published to
    // Maven Central (BSD-3-Clause per the ai-hub-apps geniex_chat_android sample it mirrors -
    // CLAUDE.md #1/#4). Runs small GGUF chat models on the Snapdragon NPU/GPU/CPU fully
    // offline; the model itself is downloaded once at runtime, not bundled in the APK.
    // Docs: https://github.com/qualcomm/ai-hub-apps/tree/main/geniex_chat_android
    implementation("com.qualcomm.qti:geniex-android:0.3.5")
    // Pulled in transitively by the GenieX SDK's data beans; declared explicitly so the
    // version is pinned. Apache-2.0.
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.3")

    debugImplementation("androidx.compose.ui:ui-tooling")

    // ── JVM unit tests (./gradlew testDebugUnitTest) ────────────────────────────────────────
    // These run the pure mesh/model/security logic on the local JVM - no device, no emulator -
    // so the dedup, envelope-parsing, rate-limiting and voice-framing code that guards untrusted
    // input (CLAUDE.md #8) is exercised on every build.
    //
    // LICENSE FLAG (CLAUDE.md #1/#6, test-only): JUnit 4 is Eclipse Public License 1.0, which is
    // outside the MIT/Apache-2.0/BSD allow-list. It is not GPL/AGPL/proprietary, it ships ONLY in
    // the test classpath (never in the APK), and it is the runner Robolectric and the Android
    // Gradle plugin require - there is no MIT/BSD/Apache substitute for it. Flagged here for a
    // human to accept before merge. Robolectric, Truth and coroutines-test below are Apache-2.0.
    testImplementation("junit:junit:4.13.2")
    // The AOSP org.json implementation, repackaged for JVM unit tests (Apache-2.0). This is the
    // SAME parser the app uses on device - NOT Douglas Crockford's reference jar, whose "shall be
    // used for Good, not Evil" clause is not OSI-approved and is disallowed by rule #1. It lets
    // SosMessage.decode() run for real on the local JVM without Robolectric.
    testImplementation("com.vaadin.external.google:android-json:0.0.20131108.vaadin1")
    // Coroutines test dispatcher for the flow-based MessageStore (Apache-2.0).
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.8.1")
    // Google Truth fluent assertions (Apache-2.0).
    testImplementation("com.google.truth:truth:1.4.4")
}
