# Installation

## Requirements

- Windows 10/11 x64 and the Steam installation of Counter-Strike 2.
- Python 3.11 **x64** for source use or building. The EXE bundles Python.
- [.NET 10 x64 runtime](https://dotnet.microsoft.com/en-us/download/dotnet/10.0) for the map converter. Building it requires the x64 SDK.
- Internet access to GitHub for the initial build-matched offset download.

## Preview the UI first

From the repository directory:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe memory_bot.py --demo
```

This preview has no game connection or input workers and uses no personal settings.

## Run from source

After installing the .NET 10 x64 SDK:

```powershell
.\.venv\Scripts\python.exe tools/build_release.py --helper-only
.\.venv\Scripts\python.exe setup_runtime.py
.\.venv\Scripts\python.exe offset_manager.py
.\.venv\Scripts\python.exe memory_bot.py
```

`setup_runtime.py` writes a map-only GSI configuration to CS2's `game/csgo/cfg` and stores a unique local token in `gsi_config.json`. An existing different GSI file is backed up under `offset_backups`. Restart CS2 after installing this configuration. Local GSI listens only on `127.0.0.1:34371`.

If automatic Steam detection fails, set the exact path for your installation before setup and launch:

```powershell
$env:CS2_STEAM_INF = 'D:\SteamLibrary\steamapps\common\Counter-Strike Global Offensive\game\csgo\steam.inf'
```

The example drive is a placeholder. Do not copy another user's GSI token or personal settings.

## Use an EXE you built

Follow [Build](BUILD.md), then extract `CS2Studio-Windows-x64.zip` into a writable folder. Keep `CS2Studio.exe` and the entire `map-tools` directory together. From that folder:

```powershell
.\CS2Studio.exe --demo
.\CS2Studio.exe --setup
.\CS2Studio.exe
```

Setup displays success or an error in a dialog. Restart CS2 after setup. On normal launch the application checks the installed game build and retrieves matching offsets. If no matching data is available, wait for the upstream providers; do not bypass version checks.

The app starts paused. F2 starts/stops, F3 shows/hides the panel and F4 toggles the automatic trigger. See [User guide](USAGE.md) before configuring input features. No anti-cheat safety is claimed.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Missing module | Install requirements with the same `.venv\Scripts\python.exe` used to launch |
| Map converter missing | Build the helper and verify .NET 10 x64, not just x86 |
| Waiting for map signal | Run setup, restart CS2, enter a map; inspect the status panel |
| Port already in use | Close another copy of this app using local port 34371 |
| Build mismatch | Wait for a matching upstream offset snapshot |
| Profile changes do not apply | Save the weapon form; check automatic profile switching and the active profile label |
| Glow flicker | The independent silhouette avoids that specific shared-field conflict but approximates the model |

Do not disable Windows security tools as an installation step. Keep only installations whose source and build you have reviewed.

## Remove the local setup

Close the app. Remove `game/csgo/cfg/gamestate_integration_cs2tool.cfg` if it belongs to this installation; restore a saved previous file if needed. Remove the app folder when no longer needed. No Windows service or scheduled task is installed.
