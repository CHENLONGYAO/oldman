$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$AndroidDir = Join-Path $Root "android"
$ApkPath = Join-Path $AndroidDir "app\build\outputs\apk\debug\app-debug.apk"

function Test-JavaHome {
    param([string] $JavaHome)

    if (-not $JavaHome) {
        return $null
    }

    $java = Join-Path $JavaHome "bin\java.exe"
    $javac = Join-Path $JavaHome "bin\javac.exe"
    if (-not (Test-Path $java) -or -not (Test-Path $javac)) {
        return $null
    }

    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $java
    $psi.Arguments = "-version"
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $proc = [System.Diagnostics.Process]::Start($psi)
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()
    $versionText = ($stdout + "`n" + $stderr).Trim()
    $major = $null
    if ($versionText -match 'version "1\.(\d+)\.') {
        $major = [int] $Matches[1]
    } elseif ($versionText -match 'version "(\d+)\.') {
        $major = [int] $Matches[1]
    }

    if ($null -eq $major) {
        return $null
    }

    [pscustomobject]@{
        Home = (Resolve-Path $JavaHome).Path
        Major = $major
        VersionText = ($versionText -split "`n")[0]
    }
}

function Get-JavaCandidates {
    $candidates = New-Object System.Collections.Generic.List[string]

    if ($env:JAVA_HOME) {
        $candidates.Add($env:JAVA_HOME)
    }

    $preferred = @(
        "$env:ProgramFiles\Android\Android Studio\jbr",
        "${env:ProgramFiles(x86)}\Android\Android Studio\jbr",
        "$env:LOCALAPPDATA\Programs\Android Studio\jbr"
    )
    foreach ($path in $preferred) {
        if ($path -and (Test-Path $path)) {
            $candidates.Add($path)
        }
    }

    $roots = @(
        "$env:ProgramFiles\Eclipse Adoptium",
        "$env:ProgramFiles\Java",
        "$env:ProgramFiles\Microsoft",
        "$env:ProgramFiles\RedHat",
        "$env:LOCALAPPDATA\Programs"
    )
    foreach ($root in $roots) {
        if (-not $root -or -not (Test-Path $root)) {
            continue
        }
        Get-ChildItem -LiteralPath $root -Directory -Recurse -Depth 2 -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match 'jdk|openjdk|temurin|zulu|java' } |
            ForEach-Object { $candidates.Add($_.FullName) }
    }

    $seen = @{}
    foreach ($candidate in $candidates) {
        if (-not $candidate) {
            continue
        }
        try {
            $resolved = (Resolve-Path $candidate -ErrorAction Stop).Path
        } catch {
            continue
        }
        if (-not $seen.ContainsKey($resolved)) {
            $seen[$resolved] = $true
            $resolved
        }
    }
}

function Select-JavaHome {
    $checked = @()
    foreach ($candidate in Get-JavaCandidates) {
        $info = Test-JavaHome $candidate
        if ($null -eq $info) {
            continue
        }
        $checked += $info
        if ($info.Major -ge 17 -and $info.Major -le 22) {
            return $info
        }
    }

    Write-Host "Checked Java installations:"
    foreach ($item in $checked) {
        Write-Host "  Java $($item.Major): $($item.Home)"
    }
    throw "No compatible JDK found. Android build needs JDK 17-22 for the pinned Gradle 8.9 wrapper. OpenJDK 8 is too old; Android Studio's bundled JBR is recommended."
}

function Select-AndroidSdk {
    $candidates = @(
        $env:ANDROID_HOME,
        $env:ANDROID_SDK_ROOT,
        "$env:LOCALAPPDATA\Android\Sdk"
    )
    foreach ($candidate in $candidates) {
        if (-not $candidate) {
            continue
        }
        $platformTools = Join-Path $candidate "platform-tools"
        $buildTools = Join-Path $candidate "build-tools"
        if ((Test-Path $platformTools) -and (Test-Path $buildTools)) {
            return (Resolve-Path $candidate).Path
        }
    }
    throw "Android SDK was not found. Open Android Studio once and install Android SDK Platform Tools / Build Tools."
}

function Select-Gradle {
    $projectWrapper = Join-Path $AndroidDir "gradlew.bat"
    if (Test-Path $projectWrapper) {
        return (Resolve-Path $projectWrapper).Path
    }

    $pathGradle = Get-Command gradle -ErrorAction SilentlyContinue
    if ($pathGradle) {
        return $pathGradle.Source
    }

    $wrapperRoot = Join-Path $env:USERPROFILE ".gradle\wrapper\dists"
    if (Test-Path $wrapperRoot) {
        $gradle = Get-ChildItem -LiteralPath $wrapperRoot -Recurse -Filter gradle.bat -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($gradle) {
            return $gradle.FullName
        }
    }

    throw "Gradle was not found. Open the android folder in Android Studio once, then run this script again."
}

if (-not (Test-Path (Join-Path $AndroidDir "settings.gradle"))) {
    throw "Android project was not found at $AndroidDir."
}

$javaInfo = Select-JavaHome
$sdkRoot = Select-AndroidSdk
$gradle = Select-Gradle

$env:JAVA_HOME = $javaInfo.Home
$env:ANDROID_HOME = $sdkRoot
$env:ANDROID_SDK_ROOT = $sdkRoot
$env:PATH = "$($javaInfo.Home)\bin;$sdkRoot\platform-tools;$env:PATH"

$localProperties = Join-Path $AndroidDir "local.properties"
$sdkDirForGradle = $sdkRoot.Replace("\", "\\")
Set-Content -LiteralPath $localProperties -Encoding ASCII -Value "sdk.dir=$sdkDirForGradle"

Write-Host "Using Java: $($javaInfo.VersionText)"
Write-Host "JAVA_HOME: $($javaInfo.Home)"
Write-Host "ANDROID_HOME: $sdkRoot"
Write-Host "Gradle: $gradle"
Write-Host ""

$hadDebug = Test-Path Env:DEBUG
$previousDebug = $env:DEBUG
# Gradle's Windows launcher echoes every batch command when DEBUG is set.
Remove-Item Env:DEBUG -ErrorAction SilentlyContinue

Push-Location $AndroidDir
try {
    & $gradle assembleDebug --stacktrace
    if ($LASTEXITCODE -ne 0) {
        throw "Gradle build failed with exit code $LASTEXITCODE."
    }
} finally {
    if ($hadDebug) {
        $env:DEBUG = $previousDebug
    } else {
        Remove-Item Env:DEBUG -ErrorAction SilentlyContinue
    }
    Pop-Location
}

if (-not (Test-Path $ApkPath)) {
    throw "Build completed but APK was not found at $ApkPath."
}

$apk = Get-Item $ApkPath
Write-Host ""
Write-Host "Done. APK:"
Write-Host "  $($apk.FullName)"
Write-Host "  $([math]::Round($apk.Length / 1KB, 1)) KB"
