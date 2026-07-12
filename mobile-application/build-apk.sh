#!/usr/bin/env bash
# Build a debug APK for the Sankat-Mochan mesh app (OnePlus / any arm64-v8a device).
# Run on a machine with Android Studio installed — it bundles JDK 17 and the Android SDK.
#
#   cd mobile-application
#   ./build-apk.sh
#
# Output: app/build/outputs/apk/debug/app-debug.apk
set -euo pipefail
cd "$(dirname "$0")"

# 1. JAVA_HOME -> Android Studio's bundled JBR (JDK 17) unless java is already on PATH.
if ! command -v java >/dev/null 2>&1 && [ -z "${JAVA_HOME:-}" ]; then
  for j in \
    "/Applications/Android Studio.app/Contents/jbr/Contents/Home" \
    "$HOME/Applications/Android Studio.app/Contents/jbr/Contents/Home" \
    "$HOME/android-studio/jbr" \
    "/opt/android-studio/jbr" \
    "/usr/local/android-studio/jbr"; do
    if [ -x "$j/bin/java" ]; then
      export JAVA_HOME="$j"
      export PATH="$j/bin:$PATH"
      echo "Using JDK: $j"
      break
    fi
  done
fi
if ! command -v java >/dev/null 2>&1 && [ -z "${JAVA_HOME:-}" ]; then
  echo "No 'java' on PATH and no Android Studio JBR found. Install Android Studio, or set JAVA_HOME to a JDK 17." >&2
  exit 1
fi

# 2. Android SDK location -> local.properties (Gradle reads sdk.dir from here). Not committed.
SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
if [ -z "$SDK" ]; then
  for s in "$HOME/Library/Android/sdk" "$HOME/Android/Sdk" "$HOME/android/sdk"; do
    [ -d "$s" ] && SDK="$s" && break
  done
fi
if [ -z "$SDK" ] || [ ! -d "$SDK" ]; then
  echo "Android SDK not found. Open this project once in Android Studio (installs the SDK), or set ANDROID_HOME." >&2
  exit 1
fi
echo "sdk.dir=$SDK" > local.properties
echo "Using SDK: $SDK"

# 3. Build the debug APK.
./gradlew :app:assembleDebug --stacktrace

APK="$(pwd)/app/build/outputs/apk/debug/app-debug.apk"
echo ""
if [ -f "$APK" ]; then
  echo "BUILT: $APK"
  echo "Install on the OnePlus:  adb install -r \"$APK\""
else
  echo "Build reported success but APK not found at $APK" >&2
  exit 1
fi
