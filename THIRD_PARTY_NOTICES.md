# Third-party notices

The project's original MIT copyright notice is retained in `LICENSE`. Changes and packaging do not replace upstream ownership.

| Component | Use / source |
| --- | --- |
| Python / Tcl-Tk | Runtime and desktop UI: https://www.python.org/ |
| Pymem 1.14.0 | Windows process access: https://github.com/srounet/Pymem |
| pygame 2.6.1 / SDL | Pixel buffers and drawing: https://www.pygame.org/ |
| PyInstaller 6.19.0 | Build tool / bootloader: https://pyinstaller.org/ |
| Pillow 12.3.0 | Development tooling only: https://python-pillow.org/ |
| ValveResourceFormat 20.0.6980 | Map resource parsing: https://github.com/ValveResourceFormat/ValveResourceFormat |
| a2x/cs2-dumper | External offset provider: https://github.com/a2x/cs2-dumper |
| sezzyaep/CS2-OFFSETS | External offset provider: https://github.com/sezzyaep/CS2-OFFSETS |

Dependencies keep their respective licenses. NuGet direct and transitive dependencies are recorded in `tools/MapGeometry/packages.lock.json`; Python direct versions are in the requirements files. Offset provider output is retrieved at runtime and is not included in this source repository.

Counter-Strike, CS2, Steam and associated game content belong to their respective owners. No game assets are distributed with this source repository. Local map conversion does not grant redistribution rights over the source game data.
