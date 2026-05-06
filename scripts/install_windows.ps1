Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$DefaultRepoUrl = "https://github.com/RSWAIN1486/sankalp.git"
$RepoUrl = if ($env:SANKALP_REPO_URL) { $env:SANKALP_REPO_URL } else { $DefaultRepoUrl }
$Branch = if ($env:SANKALP_BRANCH) { $env:SANKALP_BRANCH } else { "main" }
$AgentHome = if ($env:SANKALP_AGENT_HOME) { $env:SANKALP_AGENT_HOME } elseif ($env:SANKALP_STATE_DIR) { $env:SANKALP_STATE_DIR } else { Join-Path $env:USERPROFILE ".sankalp" }
$RootDir = $AgentHome
$StateDir = $AgentHome
$InstallDir = if ($env:SANKALP_INSTALL_DIR) { $env:SANKALP_INSTALL_DIR } else { Join-Path $AgentHome "app" }
$HostValue = if ($env:SANKALP_HOST) { $env:SANKALP_HOST } else { "127.0.0.1" }
$PortValue = if ($env:SANKALP_PORT) { $env:SANKALP_PORT } else { "8765" }
$NodeMajorRequired = 20
$PreserveLocalChanges = if ($env:SANKALP_PRESERVE_LOCAL_CHANGES) { $env:SANKALP_PRESERVE_LOCAL_CHANGES } else { "0" }
$OpenAfterInstall = if ($env:SANKALP_OPEN_AFTER_INSTALL) { $env:SANKALP_OPEN_AFTER_INSTALL } else { "1" }
$ObsidianOnboard = if ($env:SANKALP_OBSIDIAN_ONBOARD) { $env:SANKALP_OBSIDIAN_ONBOARD } else { "1" }
$DefaultInstallDir = Join-Path $AgentHome "app"

function Write-Info {
  param([string]$Message)
  Write-Host $Message
}

function Require-Tool {
  param([string]$Name, [string]$InstallHint)
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Missing required tool: $Name. $InstallHint"
  }
}

function Test-RepoCheckout {
  param([string]$Path)
  return (
    (Test-Path (Join-Path $Path ".git")) -and
    (Test-Path (Join-Path $Path "sankalp")) -and
    (Test-Path (Join-Path $Path "web"))
  )
}

function Move-LegacyPath {
  param([string]$LegacyPath)
  if (-not (Test-Path $LegacyPath)) {
    return
  }
  if ($LegacyPath -eq $AgentHome) {
    return
  }

  New-Item -Path $AgentHome -ItemType Directory -Force | Out-Null
  if ((Test-RepoCheckout -Path $LegacyPath) -and -not (Test-Path $InstallDir)) {
    Write-Info "Migrating legacy Sankalp checkout from $LegacyPath to $InstallDir"
    Move-Item -Path $LegacyPath -Destination $InstallDir
    return
  }

  $stamp = Get-Date -Format "yyyyMMddHHmmss"
  $backup = Join-Path $AgentHome "legacy-sankalp-$stamp"
  Write-Info "Moving legacy Sankalp folder to $backup"
  Move-Item -Path $LegacyPath -Destination $backup
}

function Migrate-LegacyHome {
  $legacyProfileHome = Join-Path $env:USERPROFILE "sankalp"
  if ((Test-Path $legacyProfileHome) -and -not (Test-Path $AgentHome) -and -not (Test-RepoCheckout -Path $legacyProfileHome)) {
    Write-Info "Migrating legacy Sankalp home from $legacyProfileHome to $AgentHome"
    Move-Item -Path $legacyProfileHome -Destination $AgentHome
  } else {
    Move-LegacyPath -LegacyPath $legacyProfileHome
  }

  $legacyLocalRoot = Join-Path $env:LOCALAPPDATA "Sankalp"
  $legacyLocalApp = Join-Path $legacyLocalRoot "app"
  if ((Test-Path $legacyLocalApp) -and -not (Test-Path $InstallDir)) {
    New-Item -Path $AgentHome -ItemType Directory -Force | Out-Null
    Write-Info "Migrating legacy installed app from $legacyLocalApp to $InstallDir"
    Move-Item -Path $legacyLocalApp -Destination $InstallDir
  }
  if ((Test-Path $legacyLocalRoot) -and -not (Get-ChildItem -Path $legacyLocalRoot -Force -ErrorAction SilentlyContinue)) {
    Remove-Item -Path $legacyLocalRoot -Force
  }
}

function Ensure-ManagedRepo {
  New-Item -Path (Split-Path -Parent $InstallDir) -ItemType Directory -Force | Out-Null
  if (Test-Path (Join-Path $InstallDir ".git")) {
    Write-Info "Updating Sankalp in $InstallDir"
    git -C $InstallDir fetch --prune origin
    if (($InstallDir -eq $DefaultInstallDir) -or ($env:SANKALP_FORCE_UPDATE -eq "1")) {
      if ($PreserveLocalChanges -ne "1") {
        git -C $InstallDir reset --hard HEAD
        git -C $InstallDir clean -fd
      }
      git -C $InstallDir checkout -B $Branch "origin/$Branch"
      if ($PreserveLocalChanges -ne "1") {
        git -C $InstallDir reset --hard "origin/$Branch"
        git -C $InstallDir clean -fd
      }
      return
    }
    git -C $InstallDir checkout $Branch
    git -C $InstallDir pull --ff-only origin $Branch
    return
  }

  if (Test-Path $InstallDir) {
    throw "$InstallDir exists but is not a git checkout. Move it or choose another SANKALP_INSTALL_DIR."
  }
  Write-Info "Installing Sankalp into $InstallDir"
  git clone --branch $Branch $RepoUrl $InstallDir
}

function Ensure-Node {
  $node = Get-Command node -ErrorAction SilentlyContinue
  if (-not $node) {
    throw "Node.js is required to build WebUI. Install Node 20+ and rerun."
  }
  $major = [int](node -p "Number(process.versions.node.split('.')[0])")
  if ($major -lt $NodeMajorRequired) {
    throw "Node.js $NodeMajorRequired+ required, found $major."
  }
}

function Build-WebUi {
  Write-Info "Installing WebUI dependencies"
  Push-Location (Join-Path $InstallDir "web")
  try {
    npm ci
    npm exec svelte-kit sync
    npm run build
  } finally {
    Pop-Location
  }
}

function New-Launcher {
  New-Item -Path $RootDir -ItemType Directory -Force | Out-Null
  New-Item -Path (Join-Path $RootDir "bin") -ItemType Directory -Force | Out-Null
  $launcherPath = Join-Path $RootDir "bin\sankalp-launcher.ps1"
  $cmdPath = Join-Path $RootDir "bin\sankalp.cmd"
  $launcher = @"
`$ErrorActionPreference = "SilentlyContinue"
`$hostValue = "$HostValue"
`$portValue = "$PortValue"
`$repoDir = "$InstallDir"
`$stateDir = "$StateDir"
`$url = "http://{0}:{1}" -f `$hostValue, `$portValue
New-Item -Path `$stateDir -ItemType Directory -Force | Out-Null
`$tcpReady = `$false
try {
  `$tcpReady = (Test-NetConnection -ComputerName `$hostValue -Port ([int]`$portValue) -WarningAction SilentlyContinue).TcpTestSucceeded
} catch {}
if (`$tcpReady) {
  Start-Process `$url
  exit 0
}
`$pythonExe = Join-Path `$repoDir ".venv\Scripts\python.exe"
if (-not (Test-Path `$pythonExe)) {
  if (Get-Command py -ErrorAction SilentlyContinue) {
    `$pythonExe = "py"
    `$pythonArgs = @("-3", "server.py")
  } else {
    `$pythonExe = "python"
    `$pythonArgs = @("server.py")
  }
} else {
  `$pythonArgs = @("server.py")
}
`$env:SANKALP_HOST = `$hostValue
`$env:SANKALP_PORT = `$portValue
`$env:SANKALP_STATE_DIR = `$stateDir
Start-Process -FilePath `$pythonExe -ArgumentList `$pythonArgs -WorkingDirectory `$repoDir -WindowStyle Hidden
Start-Sleep -Milliseconds 900
Start-Process `$url
"@
  Set-Content -Path $launcherPath -Value $launcher -Encoding UTF8
  Set-Content -Path $cmdPath -Value "@powershell -NoProfile -ExecutionPolicy Bypass -File `"$launcherPath`"" -Encoding ASCII

  $shortcutDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
  New-Item -Path $shortcutDir -ItemType Directory -Force | Out-Null
  $shortcutPath = Join-Path $shortcutDir "Sankalp.lnk"
  $shell = New-Object -ComObject WScript.Shell
  $shortcut = $shell.CreateShortcut($shortcutPath)
  $shortcut.TargetPath = $cmdPath
  $shortcut.WorkingDirectory = $InstallDir
  $shortcut.IconLocation = "shell32.dll,220"
  $shortcut.Save()
}

function Ensure-ObsidianSetup {
  if ($ObsidianOnboard -eq "0") {
    return
  }
  Write-Info "Checking Obsidian setup"
  Push-Location $InstallDir
  try {
    $helper = @'
import json
import os
import subprocess
from pathlib import Path
from sankalp.settings import auto_detect_obsidian_vault, load_settings, save_settings

download_url = "https://obsidian.md/download"
obsidian_registry = Path.home() / "AppData" / "Roaming" / "obsidian" / "obsidian.json"
if not obsidian_registry.exists():
    try:
        os.startfile(download_url)  # type: ignore[attr-defined]
    except Exception:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", "Start-Process", download_url],
            shell=False,
        )
    print("Obsidian is not installed. Opened download page.")
    raise SystemExit(0)

current = str(load_settings().get("obsidian_vault_path") or "").strip()
detected = auto_detect_obsidian_vault(accessible_only=True)
if detected and detected != current:
    save_settings({"obsidian_vault_path": detected})
    print(f"Auto-detected Obsidian vault: {detected}")

if os.environ.get("SANKALP_OBSIDIAN_ONBOARD", "1") == "prompt":
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$dlg = New-Object System.Windows.Forms.FolderBrowserDialog; "
        "$dlg.Description = 'Select your Obsidian vault folder for Sankalp'; "
        "$res = $dlg.ShowDialog(); "
        "if ($res -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $dlg.SelectedPath }"
    )
    result = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    selected = (result.stdout or "").strip()
    if selected:
        save_settings({"obsidian_vault_path": selected})
        print(f"Configured Obsidian vault: {selected}")
'@
    $env:SANKALP_STATE_DIR = $StateDir
    python -c $helper
  } finally {
    Pop-Location
  }
}

function Open-App {
  if ($OpenAfterInstall -ne "1") {
    return
  }
  & (Join-Path $RootDir "bin\sankalp.cmd")
}

function Test-Launcher {
  $launcherPath = Join-Path $RootDir "bin\sankalp-launcher.ps1"
  if (-not (Test-Path $launcherPath)) {
    throw "Launcher self-test failed: launcher script not found at $launcherPath"
  }

  $parseErrors = $null
  [void][System.Management.Automation.Language.Parser]::ParseFile($launcherPath, [ref]$null, [ref]$parseErrors)
  if ($parseErrors -and $parseErrors.Count -gt 0) {
    $first = $parseErrors[0]
    throw "Launcher self-test failed: PowerShell parse error at line $($first.Extent.StartLineNumber), col $($first.Extent.StartColumnNumber): $($first.Message)"
  }

  $cmdPath = Join-Path $RootDir "bin\sankalp.cmd"
  if (-not (Test-Path $cmdPath)) {
    throw "Launcher self-test failed: command shim not found at $cmdPath"
  }
  if (-not (Get-Command py -ErrorAction SilentlyContinue) -and -not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Launcher self-test failed: neither 'py' nor 'python' is available in PATH."
  }
}

Require-Tool -Name "git" -InstallHint "Install Git for Windows."
Require-Tool -Name "python" -InstallHint "Install Python 3.9+."
Require-Tool -Name "npm" -InstallHint "Install Node.js 20+."

Migrate-LegacyHome
Ensure-ManagedRepo
Ensure-Node
Build-WebUi
New-Launcher
Test-Launcher
Ensure-ObsidianSetup
Open-App

Write-Info "Sankalp installed."
Write-Info "Start Menu shortcut: Sankalp"
Write-Info "WebUI: http://$HostValue`:$PortValue"
