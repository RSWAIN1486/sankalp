# Sankalp Windows Installer

This document defines the Windows installer flow with the same managed-update behavior as
macOS.

## Goals

- Per-user install under `%LOCALAPPDATA%\Sankalp` (no admin required by default).
- Managed app checkout in `%LOCALAPPDATA%\Sankalp\app`.
- Safe reinstall/update that resets managed code while preserving user state.
- Local-first runtime with browser WebUI at `http://127.0.0.1:8765`.
- Obsidian onboarding:
  - detect if Obsidian is installed;
  - open download page if not installed;
  - auto-detect accessible vault from Obsidian registry;
  - optional folder picker prompt.
- Post-install launcher self-test:
  - validates generated `sankalp-launcher.ps1` syntax;
  - verifies `sankalp.cmd` exists;
  - verifies `py` or `python` is available in PATH.

## Direct Install Command

Run in PowerShell:

```powershell
irm https://raw.githubusercontent.com/RSWAIN1486/sankalp/main/scripts/install_windows.ps1 | iex
```

Optional installer env overrides:

```powershell
$env:SANKALP_PORT = "8766"
$env:SANKALP_OBSIDIAN_ONBOARD = "prompt"
irm https://raw.githubusercontent.com/RSWAIN1486/sankalp/main/scripts/install_windows.ps1 | iex
```

## Managed Update Semantics

- `%LOCALAPPDATA%\Sankalp\app` is managed application code.
- Reinstall/update runs `git fetch` and resets checkout to `origin/main`.
- Dirty tracked/untracked files in managed checkout are cleaned unless
  `SANKALP_PRESERVE_LOCAL_CHANGES=1`.
- User state remains outside the checkout in `%USERPROFILE%\.sankalp`.

## Build a Windows EXE Installer

This repo includes an Inno Setup script at `packaging/windows/setup.iss`.

1. Install Inno Setup.
2. In repo root on Windows, run:

```powershell
iscc packaging\windows\setup.iss
```

3. Output installer is written to:

```text
packaging\windows\dist\
```

The EXE runs `scripts/install_windows.ps1` as a hidden post-install step.
