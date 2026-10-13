"""Install per-machine map-only GSI settings without connecting to the game."""
import argparse
import json
from pathlib import Path
import secrets
import shutil
from datetime import datetime

from offset_manager import installed_build
from settings_profiles import atomic_json


def install(base, steam_inf=None):
    base = Path(base).resolve()
    game_info = Path(steam_inf) if steam_inf else installed_build()[1]
    target_dir = game_info.parent / 'cfg'
    if not game_info.is_file() or not target_dir.is_dir():
        raise FileNotFoundError('CS2 game/csgo/steam.inf or cfg directory not found')
    settings_path = base / 'gsi_config.json'
    settings = json.loads(settings_path.read_text(encoding='utf-8-sig')) if settings_path.exists() else {
        'port': 34371, 'token': secrets.token_hex(24)
    }
    port, token = settings.get('port'), settings.get('token')
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('Invalid local GSI port')
    if not isinstance(token, str) or len(token) < 24 or not all(c.isalnum() for c in token):
        raise ValueError('Invalid local GSI token')
    content = f'''"CS2 Studio map visibility"
{{
    "uri" "http://127.0.0.1:{port}/"
    "timeout" "2.0"
    "buffer" "0.0"
    "throttle" "0.1"
    "heartbeat" "1.0"
    "auth" {{ "token" "{token}" }}
    "data" {{ "map" "1" }}
}}
'''
    target = target_dir / 'gamestate_integration_cs2tool.cfg'
    if target.exists() and target.read_text(encoding='utf-8-sig') != content:
        backups = base / 'offset_backups'
        backups.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backups / f'gsi-{datetime.now():%Y%m%d-%H%M%S-%f}.cfg')
    atomic_json(settings_path, settings)
    target.write_text(content, encoding='utf-8')
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--steam-inf', type=Path)
    args = parser.parse_args()
    print('Installed:', install(args.base, args.steam_inf))
    print('Restart CS2 to load the map-only configuration.')


if __name__ == '__main__':
    main()
