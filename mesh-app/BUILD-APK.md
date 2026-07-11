# Building the mesh app APK (OnePlus / any arm64-v8a phone)

The app targets `arm64-v8a` (see `app/build.gradle.kts` → `abiFilters`), which is exactly
what OnePlus phones use — so there is **nothing device-specific to change**. A normal debug
APK sideloads straight onto the phone.

Requirements (all bundled with **Android Studio**):
- JDK **17** (Android Studio ships it as the "JBR")
- Android **SDK platform-35** + **build-tools** (installed on first project open / SDK Manager)
- Gradle 8.13 — downloaded automatically by the wrapper, no manual install

---

## Option A — one click in Android Studio (simplest)

1. Open the `mesh-app` folder in Android Studio and let it finish Gradle sync
   (this also installs the right SDK packages if they're missing).
2. **Build ▸ Build App Bundle(s) / APK(s) ▸ Build APK(s)**.
3. Click **locate** in the toast, or grab it from:
   `mesh-app/app/build/outputs/apk/debug/app-debug.apk`
4. Copy that APK to the OnePlus and install (enable "install unknown apps" for your file
   manager). Done.

## Option B — command line (uses the helper scripts here)

The scripts point `JAVA_HOME` at Android Studio's bundled JDK and write `local.properties`
with your SDK path, then run the build.

Windows (PowerShell):
```powershell
cd mesh-app
./build-apk.ps1
```

macOS / Linux:
```bash
cd mesh-app
./build-apk.sh
```

Or fully manual, if `java` (17) and the SDK are already on the machine:
```bash
cd mesh-app
echo "sdk.dir=/path/to/Android/Sdk" > local.properties   # or set ANDROID_HOME
./gradlew :app:assembleDebug        # gradlew.bat on Windows
```

Output APK (both options):
`mesh-app/app/build/outputs/apk/debug/app-debug.apk`

---

## Install on the OnePlus

- **USB (adb):** `adb install -r app/build/outputs/apk/debug/app-debug.apk`
- **Manual:** copy the APK to the phone, tap it, allow install from unknown sources.

## Release build (optional)

`./gradlew :app:assembleRelease` produces an optimized APK, but it is **unsigned** — you must
sign it with your own keystore before it will install. Debug is the right choice for testing.
