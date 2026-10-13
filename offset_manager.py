"""Download a complete, version-matched CS2 dump without running the game.

Run `python offset_manager.py` to update, or add `--offline` to verify the cache.
PatchVersion in game/csgo/steam.inf is used, not Steam's unrelated buildid.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import urllib.request
import uuid
import zipfile


SOURCES = (
    ("a2x", "a2x/cs2-dumper", "output/"),
    ("sezzyaep", "sezzyaep/CS2-OFFSETS", ""),
)
MANIFEST = "snapshot_manifest.json"
ASSET_NAME = re.compile(
    r"(?:info|offsets|buttons|interfaces|schemas|netvars|[a-z0-9_]+_dll)"
    r"\.(?:json|cs|hpp|rs|zig)\Z"
)
REQUIRED_GLOBALS = (
    "dwEntityList", "dwLocalPlayerPawn", "dwLocalPlayerController",
    "dwViewMatrix", "dwViewAngles", "dwPlantedC4",
)
REQUIRED_FIELDS = (
    ("C_BaseEntity", "m_iHealth"), ("C_BaseEntity", "m_iTeamNum"),
    ("C_BaseEntity", "m_pGameSceneNode"), ("C_BaseEntity", "m_vecVelocity"),
    ("C_BaseEntity", "m_fFlags"), ("CCSPlayerController", "m_hPlayerPawn"),
    ("CSkeletonInstance", "m_modelState"), ("C_BasePlayerPawn", "m_vOldOrigin"),
    ("C_CSPlayerPawn", "m_iIDEntIndex"), ("C_CSPlayerPawn", "m_entitySpottedState"),
    ("C_CSPlayerPawn", "m_iShotsFired"), ("C_CSPlayerPawn", "m_pAimPunchServices"),
    ("C_BaseModelEntity", "m_vecViewOffset"),
    ("CCSPlayer_AimPunchServices", "m_predictableBaseAngle"),
)


class OffsetError(RuntimeError):
    pass


def field_offset(classes, class_name, field_name):
    """Read either dumper's field format, including inherited fields."""
    requested_class = class_name
    seen = set()
    while class_name and class_name not in seen:
        seen.add(class_name)
        body = classes.get(class_name, {})
        value = body.get("fields", {}).get(field_name)
        if value is not None:
            value = value.get("offset") if isinstance(value, dict) else value
            if type(value) is int and value >= 0:
                return value
            break
        class_name = body.get("parent")
    raise OffsetError(f"Sinif alani eksik/gecersiz: {requested_class}.{field_name}")


def parse_patch_version(text):
    match = re.search(r"^PatchVersion=(1)\.(\d{2})\.(\d)\.(\d)\s*$", text, re.M)
    if not match:
        raise OffsetError("steam.inf PatchVersion bicimi taninmiyor.")
    return int("".join(match.groups()))


def installed_build():
    """Return (game build, steam.inf path); do not attach to a process."""
    override = os.environ.get("CS2_STEAM_INF")
    if override:
        path = Path(override)
        return parse_patch_version(path.read_text(encoding="utf-8-sig")), path
    roots = []
    if os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                roots.append(Path(winreg.QueryValueEx(key, "SteamPath")[0]))
        except OSError:
            pass
    program_files = os.environ.get("ProgramFiles(x86)")
    if program_files:
        roots.append(Path(program_files) / "Steam")
    libraries = list(roots)
    for root in roots:
        try:
            text = (root / "steamapps/libraryfolders.vdf").read_text(encoding="utf-8")
            libraries.extend(Path(p.replace("\\\\", "\\")) for p in
                             re.findall(r'"path"\s+"([^"\r\n]+)"', text))
        except OSError:
            pass
    for library in dict.fromkeys(libraries):
        try:
            text = (library / "steamapps/appmanifest_730.acf").read_text(encoding="utf-8")
            match = re.search(r'"installdir"\s+"([^"\r\n]+)"', text)
            folder = match[1] if match else "Counter-Strike Global Offensive"
            path = library / "steamapps/common" / folder / "game/csgo/steam.inf"
            return parse_patch_version(path.read_text(encoding="utf-8-sig")), path
        except OSError:
            continue
    raise OffsetError("Kurulu CS2 bulunamadi. CS2_STEAM_INF yolunu veya --build degerini belirtin.")


def read_url(url):
    request = urllib.request.Request(url, headers={"User-Agent": "CS2-Offset-Updater"})
    with urllib.request.urlopen(request, timeout=20) as response:
        data = response.read(64 * 1024 * 1024 + 1)
    if len(data) > 64 * 1024 * 1024:
        raise OffsetError("Indirme beklenen boyutu asti.")
    return data


def validate_info(info):
    if not isinstance(info, dict) or type(info.get("build_number")) is not int or info["build_number"] <= 0:
        raise OffsetError("Dump build_number eksik/gecersiz.")
    try:
        timestamp = datetime.fromisoformat(info["timestamp"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("timezone missing")
    except (KeyError, TypeError, ValueError) as error:
        raise OffsetError("Dump timestamp eksik/gecersiz.") from error
    return timestamp


def remote_head(source):
    name, repo, prefix = source
    commit = json.loads(read_url(f"https://api.github.com/repos/{repo}/commits/main"))["sha"]
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise OffsetError("GitHub commit kimligi gecersiz.")
    info = json.loads(read_url(f"https://raw.githubusercontent.com/{repo}/{commit}/{prefix}info.json"))
    timestamp = validate_info(info)
    return dict(source=name, repository=repo, prefix=prefix, commit=commit,
                info=info, timestamp=timestamp)


def validate_files(files, source, commit):
    try:
        info = json.loads(files["info.json"])
        validate_info(info)
        offsets = json.loads(files["offsets.json"])
        client = json.loads(files["client_dll.json"])
        classes = client["client.dll"]["classes"]
        buttons = json.loads(files["buttons.json"])
        for key in REQUIRED_GLOBALS:
            value = offsets["client.dll"][key]
            if type(value) is not int or value <= 0:
                raise OffsetError(f"Global offset gecersiz: {key}")
        for class_name, field_name in REQUIRED_FIELDS:
            field_offset(classes, class_name, field_name)
        if not buttons.get("client.dll"):
            raise OffsetError("buttons.json bos.")
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise OffsetError(f"Dump eksik veya bozuk: {error}") from error
    return dict(source=source, commit=commit, info=info, offsets=offsets,
                classes=classes, buttons=buttons)


def download_files(head):
    archive = read_url(f"https://codeload.github.com/{head['repository']}/zip/{head['commit']}")
    files = {}
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        total = 0
        for member in bundle.infolist():
            # Read only flat, named dump assets; never extract archive paths.
            relative = member.filename.partition("/")[2]
            prefix = head["prefix"]
            if not relative.startswith(prefix):
                continue
            name = relative[len(prefix):]
            if not ASSET_NAME.fullmatch(name):
                continue
            total += member.file_size
            if total > 128 * 1024 * 1024 or name in files:
                raise OffsetError("Dump arsivi gecersiz.")
            files[name] = bundle.read(member)
    snapshot = validate_files(files, head["source"], head["commit"])
    if snapshot["info"] != head["info"]:
        raise OffsetError("Commit metadata ve dump verisi uyusmuyor.")
    return files, snapshot


def read_cache(base_dir):
    output = Path(base_dir) / "output"
    manifest = json.loads((output / MANIFEST).read_bytes())
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
        raise OffsetError("Yerel manifest gecersiz.")
    source = manifest["source"]
    if (source, manifest["repository"]) not in {(s[0], s[1]) for s in SOURCES}:
        raise OffsetError("Yerel dump kaynagi taninmiyor.")
    if not isinstance(manifest["commit"], str) or not re.fullmatch(r"[0-9a-f]{40}", manifest["commit"]):
        raise OffsetError("Yerel commit kimligi gecersiz.")
    files = {}
    for name, digest in manifest["files"].items():
        if not isinstance(name, str) or not ASSET_NAME.fullmatch(name):
            raise OffsetError("Yerel manifest dosya adi gecersiz.")
        data = (output / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise OffsetError(f"Yerel dosya degismis/bozulmus: {name}")
        files[name] = data
    snapshot = validate_files(files, source, manifest["commit"])
    if snapshot["info"]["build_number"] != manifest["build_number"]:
        raise OffsetError("Yerel metadata ve dump build'i uyusmuyor.")
    return snapshot


def install_files(base_dir, files, head):
    """Stage a whole generation; preserve the previous directory for rollback."""
    base = Path(base_dir).resolve()
    output = base / "output"
    backup_root = base / "offset_backups"
    stage = Path(tempfile.mkdtemp(prefix=".offset-stage-", dir=base))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = backup_root / f"output-{stamp}-{uuid.uuid4().hex[:8]}"

    for path in (output, backup_root, backup, stage):
        if not path.resolve().is_relative_to(base) or path.resolve() == base:
            raise OffsetError("Dump hedefi calisma klasoru disinda.")
    moved = False
    try:
        for name, data in files.items():
            if not ASSET_NAME.fullmatch(name):
                raise OffsetError(f"Dump dosya adi gecersiz: {name}")
            (stage / name).write_bytes(data)
        manifest = dict(source=head["source"], repository=head["repository"],
                        commit=head["commit"], build_number=head["info"]["build_number"],
                        files={n: hashlib.sha256(d).hexdigest() for n, d in files.items()})
        (stage / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        if output.exists():
            backup_root.mkdir(exist_ok=True)
            os.replace(output, backup)
            moved = True
        try:
            os.replace(stage, output)
        except OSError:
            if moved:
                os.replace(backup, output)
            raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return backup if moved else None


def sync_legacy_exports(base_dir):
    """Keep existing *_latest.json copies current; runtime uses only output/."""
    base = Path(base_dir).resolve()
    for source, name in (("offsets.json", "offsets_latest.json"),
                         ("client_dll.json", "client_dll_latest.json")):
        target = base / name
        if not target.exists():
            continue
        data = (base / "output" / source).read_bytes()
        previous = target.read_bytes()
        if data == previous:
            continue
        backups = base / "offset_backups"
        if not backups.resolve().is_relative_to(base) or not target.resolve().is_relative_to(base):
            raise OffsetError("JSON kopyasi hedefi calisma klasoru disinda.")
        backups.mkdir(exist_ok=True)
        (backups / f"{name}.{uuid.uuid4().hex[:8]}.bak").write_bytes(previous)
        handle, temporary = tempfile.mkstemp(prefix=".offset-export-", suffix=".tmp", dir=base)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(data)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def update_offsets(base_dir, expected_build=None, offline=False, log=print):
    def finish(snapshot):
        try:
            sync_legacy_exports(base_dir)
        except (OSError, OffsetError) as error:
            log(f"Eski JSON kopyalari yenilenemedi (ana output gecerli): {error}")
        return snapshot

    if expected_build is None:
        expected_build, path = installed_build()
        log(f"Kurulu oyun: build {expected_build} ({path})")
    local = None
    try:
        candidate = read_cache(base_dir)
        if candidate["info"]["build_number"] == expected_build:
            local = candidate
        else:
            log(f"Yerel build {candidate['info']['build_number']} oyunla uyusmuyor.")
    except (OSError, ValueError, KeyError, TypeError, OffsetError) as error:
        log(f"Yerel dump dogrulanamadi: {error}")
    if offline:
        if local is None:
            raise OffsetError(f"Build {expected_build} icin dogrulanmis yerel dump yok.")
        return local
    heads = []
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        futures = [(source, pool.submit(remote_head, source)) for source in SOURCES]
        for source, future in futures:
            try:
                head = future.result()
                build = head["info"]["build_number"]
                log(f"{head['source']}: build {build}, commit {head['commit'][:7]}")
                if build == expected_build:
                    heads.append(head)
            except Exception as error:
                log(f"{source[0]} metadata alinamadi: {error}")
    for head in sorted(heads, key=lambda h: h["timestamp"], reverse=True):
        # A network failure must not downgrade a newer, verified local snapshot.
        if local and ((local["source"], local["commit"]) == (head["source"], head["commit"])
                      or validate_info(local["info"]) > head["timestamp"]):
            return finish(local)
        try:
            files, snapshot = download_files(head)
            backup = install_files(base_dir, files, head)
            if backup:
                log(f"Onceki dump yedegi: {backup}")
            log(f"{len(files)} dosya ayni commit'ten guncellendi.")
            return finish(snapshot)
        except Exception as error:
            log(f"{head['source']} dump kurulumu basarisiz: {error}")
    if local:
        log("Dogrulanmis yerel dump kullaniliyor.")
        return finish(local)
    raise OffsetError(f"Build {expected_build} icin eksiksiz dump bulunamadi; eski offsetler kullanilmadi.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=int, help="Otomatik oyun surumu tespitini gecersiz kil")
    parser.add_argument("--offline", action="store_true", help="Yalnizca yerel dump'i dogrula")
    args = parser.parse_args()
    try:
        snapshot = update_offsets(Path(__file__).resolve().parent, args.build, args.offline)
        print(f"Hazir: {snapshot['source']} / build {snapshot['info']['build_number']} / {snapshot['commit'][:7]}")
    except (OffsetError, OSError, ValueError) as error:
        parser.exit(1, f"Guncelleme durduruldu: {error}\n")


if __name__ == "__main__":
    main()
