# Architecture

| Files | Responsibility |
| --- | --- |
| `memory_bot.py` | Windows entry point, engine, startup and workers |
| `control_panel.py`, `studio_panels.py` | Tkinter controls, static palette preview, profile editor and diagnostics |
| `settings_profiles.py`, `runtime_stats.py` | Atomic local persistence, effective weapon configuration, bounded measurements |
| `focus_engine.py`, `smooth_lock.py`, `recoil_control.py` | Target scanning, tracking and recoil state |
| `flick_shot.py`, `fire_control.py`, `targeting.py` | Sequencing, shared input ownership and target validation |
| `visual_style.py`, `model_glow.py` | Contour palettes, targeting bone IDs and reversible model highlighting |
| `hotkeys.py`, `visual_context.py` | Key edges and alive/observer context |
| `offset_manager.py` | Build-matched offset fetch, schema validation and atomic cache replacement |
| `map_visibility.py`, `tools/MapGeometry/` | Map-only local GSI, static collision extraction and ray queries |
| `setup_runtime.py`, `demo_mode.py` | Per-machine setup and isolated UI preview |

Normal UI updates remain on the Tk thread. Worker state is read by the dashboard; measurements and history are bounded. Weapon overrides do not mutate the base settings object. Named settings include weapon rules and keep one undo bundle.

Only the game contour worker remains; there is no full-screen overlay or cached visual pose loop. Static geometry has the limitations documented in the README. Recoil and tracking share one camera write path per frame; the flick sequence owns input while it runs.

No game assets or precomputed map data are shipped in the source tree. Map geometry is derived from the user's local installation. The offset updater checks both supported providers and accepts a complete matching snapshot.
