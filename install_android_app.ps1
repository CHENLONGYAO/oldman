$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ApkPath = Join-Path $Root "android\app\build\outputs\apk\debug\app-debug.apk"

function Invoke-External {
    param(
        [string] $FileName,
        [string] $Arguments
    )

    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $FileName
    $psi.Arguments = $Arguments
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $proc = [System.Diagnostics.Process]::Start($psi)
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()

    [pscustomobject]@{
        ExitCode = $proc.ExitCode
        Stdout = $stdout
        Stderr = $stderr
    }
}

if (-not (Test-Path $ApkPath)) {
    Write-Host "APK not found. Building first..."
    & (Join-Path $Root "build_android_app.ps1")
}

$sdkRoot = $env:ANDROID_HOME
if (-not $sdkRoot) {
    $sdkRoot = $env:ANDROID_SDK_ROOT
}
if (-not $sdkRoot) {
    $sdkRoot = Join-Path $env:LOCALAPPDATA "Android\Sdk"
}

$adb = Join-Path $sdkRoot "platform-tools\adb.exe"
if (-not (Test-Path $adb)) {
    throw "adb.exe was not found. Install Android Platform Tools in Android Studio."
}

$devicesResult = Invoke-External $adb "devices -l"
if ($devicesResult.Stderr.Trim()) {
    Write-Host $devicesResult.Stderr.Trim()
}
if ($devicesResult.ExitCode -ne 0) {
    throw "adb devices failed with exit code $($devicesResult.ExitCode)."
}

$devicesOutput = $devicesResult.Stdout -split "`r?`n"
$devices = $devicesOutput | Where-Object { $_ -match "\sdevice\s" }
if (-not $devices) {
    Write-Host "No Android device is connected."
    Write-Host "Enable USB debugging, connect the phone, and accept the authorization prompt."
    Write-Host ""
    Write-Host ($devicesOutput -join "`n")
    exit 1
}

Write-Host "Installing APK:"
Write-Host "  $ApkPath"
$installResult = Invoke-External $adb ('install -r "' + $ApkPath + '"')
if ($installResult.Stdout.Trim()) {
    Write-Host $installResult.Stdout.Trim()
}
if ($installResult.Stderr.Trim()) {
    Write-Host $installResult.Stderr.Trim()
}
if ($installResult.ExitCode -ne 0) {
    throw "adb install failed with exit code $($installResult.ExitCode)."
}

Write-Host "Launching SmartRehab..."
$launchResult = Invoke-External $adb "shell monkey -p com.smartrehab.app -c android.intent.category.LAUNCHER 1"
if ($launchResult.Stdout.Trim()) {
    Write-Host $launchResult.Stdout.Trim()
}
if ($launchResult.Stderr.Trim()) {
    Write-Host $launchResult.Stderr.Trim()
}
Write-Host "Done."
