import json
from pathlib import Path
import tempfile
import unittest

from setup_runtime import install, load_settings


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game = self.root / 'game/csgo'
        (self.game / 'cfg').mkdir(parents=True)
        self.inf = self.game / 'steam.inf'
        self.inf.write_text('PatchVersion=1.41.9.0', encoding='utf-8')
        self.base = self.root / 'app'

    def test_new_install_creates_unique_local_token_and_reuses_it(self):
        target = install(self.base, self.inf)
        settings = json.loads((self.base / 'gsi_config.json').read_text())
        content = target.read_text()
        self.assertIn(settings['token'], content)
        self.assertIn('127.0.0.1:34371', content)
        self.assertIn('"map" "1"', content)
        self.assertNotIn('player', content)
        self.assertEqual(install(self.base, self.inf).read_text(), content)
        other = self.root / 'other'
        install(other, self.inf)
        self.assertNotEqual(settings['token'], json.loads((other / 'gsi_config.json').read_text())['token'])

    def test_existing_game_config_is_backed_up_before_replacing(self):
        target = self.game / 'cfg/gamestate_integration_cs2tool.cfg'
        target.write_text('previous settings', encoding='utf-8')
        install(self.base, self.inf)
        backups = list((self.base / 'offset_backups').glob('*.cfg'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), 'previous settings')

    def test_invalid_config_does_not_modify_game_file(self):
        target = install(self.base, self.inf)
        original = target.read_bytes()
        (self.base / 'gsi_config.json').write_text('{"port": 34371, "token": "bad"}')
        with self.assertRaises(ValueError):
            install(self.base, self.inf)
        self.assertEqual(target.read_bytes(), original)

    def test_moved_install_recovers_same_connection_without_touching_game_config(self):
        target=install(self.base,self.inf)
        original=target.read_bytes()
        settings=load_settings(self.base,self.inf)
        moved=self.root/'moved'
        self.assertEqual(load_settings(moved,self.inf),settings)
        self.assertEqual(json.loads((moved/'gsi_config.json').read_text()),settings)
        self.assertEqual(target.read_bytes(),original)

    def test_existing_invalid_settings_are_not_replaced_by_recovery(self):
        install(self.base,self.inf)
        path=self.base/'gsi_config.json'
        path.write_text('{invalid')
        with self.assertRaises(ValueError): load_settings(self.base,self.inf)
        self.assertEqual(path.read_text(),'{invalid')

    def test_missing_or_remote_integration_is_not_imported(self):
        with self.assertRaises(FileNotFoundError):load_settings(self.base,self.inf)
        target=install(self.base,self.inf)
        for uri in ('http://example.com:34371/','http://127.0.0.1:80/'):
            original=target.read_text()
            target.write_text(original.replace('http://127.0.0.1:34371/',uri))
            with self.assertRaises(ValueError):load_settings(self.root/'moved',self.inf)
            self.assertFalse((self.root/'moved/gsi_config.json').exists())
            target.write_text(original)
