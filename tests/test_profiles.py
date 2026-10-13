import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from memory_bot import Config
from settings_profiles import ProfileStore,WeaponRuntime,atomic_json,settings_snapshot
from runtime_stats import RuntimeStats


def config():
    cfg=SimpleNamespace(**settings_snapshot(Config),enabled=True)
    cfg.save=Mock(return_value=True)
    return cfg


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'profiles.json'
        self.cfg=config();self.cfg.fov=170;self.cfg.aim_max_speed=201;self.cfg.rcs_scale=120
        self.store=ProfileStore(self.path,self.cfg)

    def test_initial_backup_exactly_preserves_values_without_saving_config(self):
        self.assertEqual(self.store.data['settings']['Başlangıç ayarlarım']['values'],settings_snapshot(self.cfg))
        self.cfg.save.assert_not_called()
        self.assertNotIn('enabled',self.store.data['settings']['Başlangıç ayarlarım']['values'])

    def test_weapon_switch_changes_effective_values_without_touching_general_config(self):
        before=settings_snapshot(self.cfg)
        self.store.save_weapon('weapon:9',{'fov':45,'target_bone':4,'rcs_scale':80})
        runtime=WeaponRuntime(self.cfg,self.store)
        runtime.select(9);view=runtime.view()
        self.assertEqual((view.fov,view.target_bone,view.rcs_scale),(45,4,80))
        self.assertEqual(view.aim_key,self.cfg.aim_key)
        runtime.select(7);self.assertEqual(runtime.view().fov,170)
        self.assertEqual(settings_snapshot(self.cfg),before)
        self.cfg.save.assert_not_called()

    def test_group_then_weapon_precedence_and_disable_fall_back(self):
        self.store.save_weapon('group:Keskin nişancı',{'fov':90,'target_bone':4})
        self.store.save_weapon('weapon:9',{'fov':45})
        runtime=WeaponRuntime(self.cfg,self.store);runtime.select(9)
        self.assertEqual((runtime.view().fov,runtime.view().target_bone),(45,4))
        self.assertEqual(self.store.weapon_values('weapon:9',self.cfg)['target_bone'],4)
        runtime.select(40);self.assertEqual(runtime.view().fov,90)
        self.cfg.weapon_profiles_enabled=False;self.assertEqual(runtime.view().fov,170)

    def test_current_view_keeps_atomic_override_and_reads_live_enabled_flag(self):
        self.store.save_weapon('weapon:9',{'fov':45})
        runtime=WeaponRuntime(self.cfg,self.store);runtime.select(9);view=runtime.view()
        self.store.save_weapon('weapon:9',{'fov':60})
        self.cfg.enabled=False
        self.assertEqual(view.fov,45);self.assertFalse(view.enabled)
        self.assertEqual(runtime.view().fov,60)

    def test_round_trip_settings_weapons_and_undo_preserve_active_state(self):
        self.store.save_weapon('weapon:9',{'fov':45})
        self.store.save_settings('Özel profil',self.cfg)
        self.cfg.fov=400;self.store.save_weapon('weapon:9',{'fov':90})
        self.store.apply_settings('Özel profil',self.cfg)
        self.assertEqual(self.cfg.fov,170)
        self.assertEqual(self.store.data['weapons']['weapon:9']['fov'],45)
        self.assertTrue(self.cfg.enabled)
        self.store.apply_settings(None,self.cfg,undo=True)
        self.assertEqual(self.cfg.fov,400)
        self.assertEqual(self.store.data['weapons']['weapon:9']['fov'],90)
        loaded=ProfileStore(self.path,self.cfg)
        self.assertFalse(loaded.error)
        self.assertIn('Özel profil',loaded.data['settings'])

    def test_initial_backup_cannot_be_overwritten_or_deleted(self):
        with self.assertRaises(ValueError):self.store.save_settings('Başlangıç ayarlarım',self.cfg)
        with self.assertRaises(ValueError):self.store.remove_settings('Başlangıç ayarlarım')

    def test_invalid_override_rejected_without_writing_any_file(self):
        before=self.path.read_bytes()
        for values in ({'fov':float('nan')},{'fov':999},{'rcs_enabled':1},{'enabled':True},
                       {'aim_key':1},{'team_mode':0},{'target_bone':999}):
            with self.subTest(values=values),self.assertRaises(ValueError):self.store.save_weapon('weapon:9',values)
        self.assertEqual(self.path.read_bytes(),before)

    def test_corrupt_profile_file_is_kept_and_never_replaced_on_save(self):
        self.path.write_text('{invalid',encoding='utf-8')
        store=ProfileStore(self.path,self.cfg)
        self.assertTrue(store.error)
        with self.assertRaises(ValueError):store.save_settings('test',self.cfg)
        self.assertEqual(self.path.read_text(),'{invalid')

    def test_atomic_write_failure_keeps_original_and_cleans_temporary_file(self):
        before=self.path.read_bytes()
        with patch('settings_profiles.os.replace',side_effect=PermissionError('locked')):
            with self.assertRaises(OSError):self.store.save_weapon('weapon:9',{'fov':90})
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(list(self.path.parent.glob('*.tmp')),[])
        self.assertEqual(self.store.data['weapons'],{})

    def test_failed_general_settings_save_rolls_back_in_memory_and_rules(self):
        self.store.save_settings('saved',self.cfg)
        self.cfg.fov=400;self.store.save_weapon('weapon:9',{'fov':90})
        self.cfg.save.return_value=False
        with self.assertRaises(OSError):self.store.apply_settings('saved',self.cfg)
        self.assertEqual(self.cfg.fov,400)
        self.assertEqual(self.store.data['weapons']['weapon:9']['fov'],90)

    def test_weapon_observation_reads_definition_only_on_identity_change(self):
        eng=SimpleNamespace(client=0,entity_from_index=Mock(return_value=100),_f=lambda *args:10,
                            read_bytes=Mock(return_value=b'\x09\0'))
        runtime=WeaponRuntime(self.cfg,self.store)
        for tick in range(100):runtime.observe(eng,1,2,3,tick/120)
        eng.read_bytes.assert_called_once_with(130,2)
        self.assertEqual(runtime.weapon_name,'AWP')
        runtime.observe(eng,1,4,3,1)
        self.assertEqual(eng.read_bytes.call_count,2)

    def test_failed_observation_drops_profile_and_retries_without_busy_reads(self):
        eng=SimpleNamespace(client=0,entity_from_index=Mock(return_value=100),_f=lambda *args:10,
                            read_bytes=Mock(side_effect=OSError('read failed')))
        runtime=WeaponRuntime(self.cfg,self.store)
        runtime.select(9)
        for tick in range(50):runtime.observe(eng,1,2,3,tick/120)
        self.assertIsNone(runtime.weapon_id)
        self.assertEqual(eng.read_bytes.call_count,1)
        runtime.observe(eng,1,2,3,.6)
        self.assertEqual(eng.read_bytes.call_count,2)


class DiagnosticTests(unittest.TestCase):
    def test_repeated_identical_status_does_not_grow_history(self):
        stats=RuntimeStats()
        for _ in range(10000):stats.status('Aim','Waiting')
        self.assertEqual(len(stats.snapshot()[1]),1)
        for i in range(10000):stats.status('Aim',str(i))
        self.assertEqual(len(stats.snapshot()[1]),30)

    def test_timing_samples_bounded_and_stale_samples_hidden(self):
        stats=RuntimeStats()
        for i in range(10000):stats.timing('Aim',.001,now=10)
        self.assertEqual(len(stats.timings['Aim']),240)
        self.assertEqual(stats.sample(now=10,cpu=0,memory=(10,20),cores=4)['stages']['Aim']['mean'],1)
        self.assertIsNone(stats.sample(now=14,cpu=.1,memory=(10,20),cores=4)['stages']['Aim'])

    def test_cpu_normalization_and_sampling_rate(self):
        stats=RuntimeStats()
        self.assertIsNone(stats.sample(now=1,cpu=0,memory=(10,20),cores=4)['cpu'])
        value=stats.sample(now=2,cpu=1,memory=(11,21),cores=4)
        self.assertEqual(value['cpu'],25)
        self.assertEqual(value['rss'],11)
        self.assertIs(stats.sample(now=2.5,cpu=2,memory=(12,22),cores=4),value)


if __name__=='__main__':unittest.main()
