"""Build a clean Windows package with no personal settings or game assets."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True)


def find_dotnet():
    x64 = Path(os.environ.get('ProgramW6432', r'C:\Program Files')) / 'dotnet/dotnet.exe'
    candidate = str(x64) if x64.is_file() else shutil.which('dotnet')
    if not candidate:
        raise SystemExit('Install the .NET 10 x64 SDK to build MapGeometry.')
    return candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--helper-only', action='store_true', help='Build map-tools for running Python source')
    args = parser.parse_args()
    destination = ROOT / ('map-tools' if args.helper_only else 'dist/map-tools')
    run(find_dotnet(), 'publish', 'tools/MapGeometry/MapGeometry.csproj', '-c', 'Release',
        '-r', 'win-x64', '--self-contained', 'false', '-p:RestoreLockedMode=true', '-o', destination)
    if args.helper_only:
        return
    run(sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-q')
    os.environ.setdefault('PYINSTALLER_CONFIG_DIR', str(ROOT / 'build/pyinstaller-cache'))
    run(sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm', 'CS2Studio.spec')
    release = ROOT / 'release'
    release.mkdir(exist_ok=True)
    archive = release / 'CS2Studio-Windows-x64.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(ROOT / 'dist/CS2Studio.exe', 'CS2Studio/CS2Studio.exe')
        for file in sorted(destination.rglob('*')):
            if file.is_file() and file.suffix.lower() != '.pdb':
                bundle.write(file, 'CS2Studio/map-tools/' + file.relative_to(destination).as_posix())
        for file in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'docs/INSTALL.md', 'docs/INSTALL.tr.md'):
            bundle.write(ROOT / file, 'CS2Studio/' + Path(file).name)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (release / 'SHA256SUMS.txt').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    print('Package:', archive)
    print('SHA256:', digest)


if __name__ == '__main__':
    main()
