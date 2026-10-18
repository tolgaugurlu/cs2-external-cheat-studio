# Build the Windows EXE

Use Python 3.11 x64 and the .NET 10 x64 SDK. Work from a clean source checkout:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe tools/build_release.py
```

The build script compiles the C# map helper using the NuGet lock file, runs the Python tests, packages `memory_bot.py` with PyInstaller, and creates:

```text
dist/
  StudioPanel-1.1.2.exe
  map-tools/
release/
  StudioPanel-1.1.2-Windows-x64.zip
  SHA256SUMS.txt
```

The ZIP uses an explicit file allowlist. It excludes saved settings, profiles, tokens, logs, downloaded offsets and local map caches. Each user runs `StudioPanel-1.1.2.exe --setup` to create their own local configuration.

`app_version.py` supplies the application name and version for the filename, window title and Windows file properties. Future builds use the same `StudioPanel-<version>.exe` format.

Check the resulting UI without connecting to a game:

```powershell
.\dist\StudioPanel-1.1.2.exe --demo
Get-FileHash .\release\StudioPanel-1.1.2-Windows-x64.zip -Algorithm SHA256
```

Compare the hash with `release/SHA256SUMS.txt`. A matching hash confirms file integrity, not anti-cheat safety.

## Individual checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe tools/check_studio_layout.py
.\.venv\Scripts\python.exe tools/demo.py
```

`--startup-check` also exercises the packaged UI, contour controls and hotkeys but expects a locally installed game and matching offsets; it can retrieve missing offset data. It does not run input workers. Use `--demo` for a completely game-independent preview.

## Scope of reproducibility

The direct Python dependencies and NuGet graph are pinned. PyInstaller output can vary with Python patch versions, transitive packages and the Windows build environment. This is a repeatable procedure, not a claim of byte-for-byte reproducible binaries. Build from source if you need to inspect exactly what is included.
