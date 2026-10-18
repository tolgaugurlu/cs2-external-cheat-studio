import ast
import json
import math
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from focus_engine import TargetScan, step_angles
from smooth_lock import SmoothLock, angle_delta


class MotionTests(unittest.TestCase):
    def test_monotonic_settling_without_overshoot_or_initial_snap(self):
        tracker=SmoothLock();current=(0.,0.);previous=0
        for i in range(40):
            current=tracker.step('pawn',current,(0,20),1/120)
            self.assertGreaterEqual(current[1],previous)
            self.assertLessEqual(current[1],20)
            if i==0: self.assertLess(current[1],3)
            previous=current[1]
        self.assertEqual(current,(0,20))

    def test_same_settling_time_at_different_update_rates(self):
        results=[]
        for hz in (60,120,240):
            tracker=SmoothLock();current=(0.,0.)
            for _ in range(round(.1*hz)):
                current=tracker.step('pawn',current,(0,20),1/hz)
            results.append(current[1])
        self.assertLess(max(results)-min(results),1e-8)

    def test_moving_point_tracks_without_old_smoothing_lag(self):
        tracker=SmoothLock();current=(0.,0.);legacy=(0.,0.)
        errors=[];legacy_errors=[]
        for i in range(240):
            desired=(0,30*(i+1)/120)
            current=tracker.step('pawn',current,desired,1/120)
            legacy=step_angles(legacy,desired,1/120,False,12,999)
            if i>120:
                errors.append(abs(desired[1]-current[1]))
                legacy_errors.append(abs(desired[1]-legacy[1]))
        self.assertLess(sum(errors)/len(errors),.1)
        self.assertLess(sum(errors),sum(legacy_errors)/10)

    def test_high_frequency_point_jitter_is_attenuated(self):
        tracker=SmoothLock();current=(0.,0.);samples=[]
        for i in range(240):
            desired=(0,.12*math.sin(2*math.pi*30*i/120))
            current=tracker.step('pawn',current,desired,1/120)
            if i>120: samples.append(current[1])
        self.assertLess(max(map(abs,samples)),.03)

    def test_full_identity_and_point_changes_reset_old_motion(self):
        tracker=SmoothLock();current=(0.,0.)
        for i in range(10): current=tracker.step(('pawn',6),current,(0,20+i),1/120)
        desired=(0,-15)
        result=tracker.step(('pawn',4),current,desired,1/120)
        expected=SmoothLock().step(('pawn',4),current,desired,1/120)
        self.assertEqual(result,expected)

    def test_reversal_does_not_coast_away_from_target(self):
        tracker=SmoothLock();current=(0.,0.)
        for i in range(10): current=tracker.step('pawn',current,(0,20+i),1/120)
        previous=current[1]
        for _ in range(20):
            current=tracker.step('pawn',current,(0,-10),1/120)
            self.assertLessEqual(current[1],previous)
            self.assertGreaterEqual(current[1],-10)
            previous=current[1]

    def test_combined_angular_speed_is_bounded_and_wrap_takes_short_path(self):
        current=(0.,0.);tracker=SmoothLock()
        for _ in range(20):
            result=tracker.step('pawn',current,(70,100),1/120,max_speed=120)
            self.assertLessEqual(math.hypot(*angle_delta(result,current)),1.000001)
            current=result
        result=SmoothLock().step('pawn',(0,179),(0,-179),1/120)
        self.assertGreater(angle_delta(result,(0,179))[1],0)
        self.assertLess(angle_delta(result,(0,179))[1],2)

    def test_bad_sample_is_rejected_and_pause_discards_velocity(self):
        tracker=SmoothLock()
        with self.assertRaises(ValueError): tracker.step('pawn',(0,0),(0,float('nan')),.01)
        tracker.step('pawn',(0,0),(0,20),.01)
        result=tracker.step('pawn',(0,1),(0,20),.2)
        self.assertEqual(result,SmoothLock().step('pawn',(0,1),(0,20),.2))


class LockTests(unittest.TestCase):
    def choose(self, scanner, candidates, geometry, **options):
        return scanner.choose(candidates,6,(0,0,0),lambda p:p[:2],geometry,(0,0),100,seconds=1,**options)

    def test_acquisition_scores_head_instead_of_extended_limb(self):
        candidates=[((1,10,20,30,40),{6:(10,0,7)}),
                    ((2,11,21,31,41),{6:(40,0,7),11:(0,0,4)})]
        result=self.choose(TargetScan(),candidates,SimpleNamespace(visible=lambda e,p:True))
        self.assertEqual(result[0],1)

    def test_crossing_player_and_caller_lost_index_do_not_steal_fresh_lock(self):
        scan=TargetScan();geometry=SimpleNamespace(visible=lambda e,p:True)
        a=((1,10,20,30,40),{6:(10,0,7)})
        b=((2,11,21,31,41),{6:(40,0,7)})
        self.assertEqual(self.choose(scan,[a,b],geometry)[0],1)
        b=(b[0],{6:(1,0,7)})
        self.assertEqual(self.choose(scan,[b,a],geometry,locked=-1)[0],1)

    def test_recycled_player_slot_does_not_inherit_old_lock(self):
        scan=TargetScan();geometry=SimpleNamespace(visible=lambda e,p:True)
        a=((1,10,20,30,40),{6:(10,0,7)})
        self.choose(scan,[a],geometry)
        replacement=((1,100,20,300,40),{6:(40,0,7)})
        closer=((2,11,21,31,41),{6:(1,0,7)})
        self.assertEqual(self.choose(scan,[replacement,closer],geometry)[0],2)

    def test_visible_fallback_stays_stable_until_head_is_consistently_clear(self):
        scan=TargetScan();candidate=((1,10,20,30,40),{6:(20,0,7),4:(20,0,4)})
        head_clear=False
        geometry=SimpleNamespace(visible=lambda e,p:p[2]<6 or head_clear)
        with patch('focus_engine.time.monotonic',return_value=1):
            self.assertEqual(self.choose(scan,[candidate],geometry)[5][0],4)
        for now,head_clear in ((1.01,True),(1.02,False),(1.03,True),(1.05,True)):
            with patch('focus_engine.time.monotonic',return_value=now):
                self.assertEqual(self.choose(scan,[candidate],geometry)[5][0],4)
        head_clear=True
        with patch('focus_engine.time.monotonic',return_value=1.10):
            self.assertEqual(self.choose(scan,[candidate],geometry)[5][0],6)

    def test_previous_lock_never_authorizes_hidden_point(self):
        scan=TargetScan();candidate=((1,10,20,30,40),{6:(20,0,7)})
        geometry=SimpleNamespace(visible=lambda e,p:True)
        self.assertIsNotNone(self.choose(scan,[candidate],geometry))
        geometry.visible=lambda e,p:False
        self.assertIsNone(self.choose(scan,[candidate],geometry))
        self.assertIsNone(scan.lock_key)


class ConfigurationTests(unittest.TestCase):
    def load(self,settings):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'ayar.json'
            path.write_text(json.dumps(settings,ensure_ascii=False),encoding='utf-8-sig')
            source=Path(__file__).resolve().parents[1]/'memory_bot.py'
            tree=ast.parse(source.read_text(encoding='utf-8-sig'))
            node=next(n for n in tree.body if getattr(n,'name',None)=='Config')
            from flick_shot import FLICK_KEYS
            ns={'os':os,'json':json,'CONFIG_FILE':str(path),'FLICK_KEYS':FLICK_KEYS}
            exec(compile(ast.Module(body=[node],type_ignores=[]),'memory_bot.py','exec'),ns)
            cfg=ns['Config'];cfg.load()
            return cfg

    def test_existing_settings_get_smooth_profile_without_changing_keys_or_palette(self):
        cfg=self.load({'aim_response':'Ayarlanabilir','smooth':1,'speed_cap':250,
                       'aim_key':17,'esp_palette':'Beyaz / Mavi','fov':254,'target_bone':6})
        self.assertEqual((cfg.aim_response,cfg.aim_settle_ms,cfg.aim_max_speed),('Akıcı takip',90,720))
        self.assertEqual((cfg.aim_key,cfg.esp_palette,cfg.fov,cfg.target_bone),(17,'Beyaz / Mavi',254,6))

    def test_saved_explicit_profile_selection_is_not_overridden_on_next_start(self):
        cfg=self.load({'aim_tuning_version':1,'aim_response':'Ayarlanabilir',
                       'aim_settle_ms':130,'aim_max_speed':450})
        self.assertEqual((cfg.aim_response,cfg.aim_settle_ms,cfg.aim_max_speed),('Ayarlanabilir',130,450))

    def test_turkish_settings_survive_utf8_save_and_reload(self):
        cfg=self.load({'aim_tuning_version':1,'aim_response':'Akıcı takip','esp_palette':'Altın / Mavi',
                       'esp_render_mode':'Kararlı siluet','ghost_esp':True,'glow_chams':True})
        self.assertEqual((cfg.aim_response,cfg.esp_palette),('Akıcı takip','Altın / Mavi'))
        self.assertTrue(cfg.glow_chams)
        self.assertFalse(hasattr(cfg,'esp_render_mode'))
        self.assertFalse(hasattr(cfg,'ghost_esp'))

    def test_ignored_legacy_recoil_gain_migrates_to_previous_effective_strength(self):
        cfg=self.load({'rcs_scale':129,'rcs_yaw_scale':70})
        self.assertEqual((cfg.rcs_scale,cfg.rcs_yaw_scale,cfg.rcs_tuning_version),(100,100,1))
        cfg=self.load({'rcs_scale':80,'rcs_yaw_scale':65,'rcs_tuning_version':1})
        self.assertEqual((cfg.rcs_scale,cfg.rcs_yaw_scale),(80,65))

    def test_unused_legacy_flick_gets_side_button_without_changing_active_tuning(self):
        cfg=self.load({'flick_enabled':False,'flick_key':17,'aim_key':17,'fov':170,
                       'rcs_scale':150,'rcs_yaw_scale':150,'rcs_tuning_version':1})
        self.assertEqual((cfg.flick_key,cfg.flick_knife_key,cfg.flick_version),(6,51,1))
        self.assertFalse(cfg.flick_enabled)
        self.assertEqual((cfg.aim_key,cfg.fov,cfg.rcs_scale,cfg.rcs_yaw_scale),(17,170,150,150))

    def test_active_legacy_binding_and_new_explicit_flick_settings_are_preserved(self):
        cfg=self.load({'flick_enabled':True,'flick_key':5})
        self.assertEqual(cfg.flick_key,5)
        cfg=self.load({'flick_version':1,'flick_key':17,'flick_knife_key':86,'flick_fov':180,'flick_bone':4,'flick_rearm_key':70})
        self.assertEqual((cfg.flick_key,cfg.flick_knife_key,cfg.flick_fov,cfg.flick_bone),(17,86,180,4))
        self.assertEqual(cfg.flick_rearm_key,70)


if __name__=='__main__': unittest.main()
