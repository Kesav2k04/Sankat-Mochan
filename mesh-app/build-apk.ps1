# Build a debug APK for the Sankat-Mochan mesh app (OnePlus / any arm64-v8a device).
# Run on a machine with Android Studio installed — it bundles JDK 17 and the Android SDK.
#
#   cd mesh-app
#   ./build-apk.ps1
#
# Output: app\build\outputs\apk\debug\app-debug.apk
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

# 1. JAVA_HOME -> Android Studio's bundled JBR (JDK 17) unless java 17 is already on PATH.
if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
    $candidates = @(
        "$env:ProgramFiles\Android\Android Studio\jbr",
        "$env:LOCALAPPDATA\Programs\Android Studio\jbr",
        "${env:ProgramFiles(x86)}\Android\Android Studio\jbr"
    )
    $jbr = $candidates | Where-Object { Test-Path (Join-Path $_ 'bin\java.exe') } | Select-Object -First 1
    if (-not $jbr) {
        throw "No 'java' on PATH and no Android Studio JBR found. Install Android Studio, or set JAVA_HOME to a JDK 17."
    }
    $env:JAVA_HOME = $jbr
    $env:PATH = "$jbr\bin;$env:PATH"
    Write-Host "Using JDK: $jbr"
}

# 2. Android SDK location -> local.properties (Gradle reads sdk.dir from here). Not committed.
$sdk = $env:ANDROID_HOME
if (-not $sdk) { $sdk = $env:ANDROID_SDK_ROOT }
if (-not $sdk) { $sdk = Join-Path $env:LOCALAPPDATA 'Android\Sdk' }
if (-not (Test-Path $sdk)) {
    throw "Android SDK not found at '$sdk'. Open this project once in Android Studio (installs the SDK), or set ANDROID_HOME."
}
# local.properties wants a Windows path with escaped backslashes.
$sdkEscaped = $sdk -replace '\\', '\\'
Set-Content -Path (Join-Path $PSScriptRoot 'local.properties') -Value "sdk.dir=$sdkEscaped" -Encoding ASCII
Write-Host "Using SDK: $sdk"

# 3. Build the debug APK.
& (Join-Path $PSScriptRoot 'gradlew.bat') ':app:assembleDebug' '--stacktrace'
if ($LASTEXITCODE -ne 0) { throw "Gradle build failed (exit $LASTEXITCODE)." }

$apk = Join-Path $PSScriptRoot 'app\build\outputs\apk\debug\app-debug.apk'
Write-Host ""
if (Test-Path $apk) {
    Write-Host "BUILT: $apk"
    Write-Host "Install on the OnePlus:  adb install -r `"$apk`""
} else {
    throw "Build reported success but APK not found at $apk"
}
