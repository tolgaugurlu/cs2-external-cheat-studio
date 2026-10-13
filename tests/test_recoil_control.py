import math
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from focus_engine import aim_loop
from recoil_control import RecoilControl
from smooth_lock import SmoothLock, normalized


class RecoilTests(unittest.TestCase):
    def test_first_shot_is_corrected_after_idle_sample(self):
        r=RecoilControl()
        self.assertEqual(r.sample('gun',0,(0,0),1)[1],(0,0))
        self.assertEqual(r.sample('gun',1,(1,.25),1.01),((2,.5),(2,.5)))
        self.assertEqual(r.sample('gun',2,(1.5,.4),1.02)[1],(1,.30000000000000004))

    def test_joining_mid_burst_does_not_replay_accumulated_punch(self):
        r=RecoilControl()
        self.assertEqual(r.sample('gun',15,(8,2),1)[1],(0,0))
        self.assertEqual(r.sample('gun',16,(8.1,2.1),1.01)[1],(.1999999999999993,.20000000000000018))

    def test_weapon_respawn_pause_and_shot_counter_reset_drop_old_delta(self):
        for identity,shots,now in [('new',4,1.02),('gun',4,1.2),('gun',1,1.02)]:
            r=RecoilControl();r.sample('gun',3,(2,1),1)
            self.assertEqual(r.sample(identity,shots,(.5,.2),now)[1],(0,0))
        r.reset()
        self.assertEqual(r.sample('gun',8,(3,1),1.3)[1],(0,0))

    def test_end_of_burst_never_kicks_camera_back(self):
        r=RecoilControl();r.sample('gun',5,(3,1),1)
        self.assertEqual(r.sample('gun',0,(2,.5),1.01),((0,0),(0,0)))
        self.assertEqual(r.sample('gun',1,(.5,.1),1.02)[1],(1,.2))

    def test_independent_gains_and_gain_changes_do_not_replay_delta(self):
        r=RecoilControl();r.sample('gun',0,(0,0),1,50,0)
        self.assertEqual(r.sample('gun',1,(1,1),1.01,50,0),((1,0),(1,0)))
        self.assertEqual(r.sample('gun',2,(1.2,1.2),1.02,100,100)[1],(0,0))

    def test_corrupt_samples_reset_instead_of_causing_or_deferring_a_jump(self):
        for bad in ((float('nan'),0),(31,0),(5,5)):
            r=RecoilControl();r.sample('gun',0,(0,0),1)
            with self.assertRaises(ValueError):r.sample('gun',1,bad,1.01)
            self.assertEqual(r.sample('gun',2,(1,.5),1.02)[1],(0,0))

    def test_recoil_is_not_delayed_by_smooth_target_tracking(self):
        for hz in (60,120,240):
            r=RecoilControl();motion=SmoothLock();current=(0,0)
            r.sample('gun',0,(0,0),1)
            for step in range(1,hz):
                punch=(2*step/hz,.3*math.sin(step/hz))
                offset,delta=r.sample('gun',1+step//8,punch,1+step/hz)
                visual=normalized(tuple(current[i]-delta[i]+offset[i] for i in range(2)))
                tracked=motion.step('enemy',visual,(0,0),1/hz,150,720)
                current=normalized(tuple(tracked[i]-offset[i] for i in range(2)))
                self.assertAlmostEqual(current[0]+offset[0],0,places=7)
                self.assertAlmostEqual(current[1]+offset[1],0,places=7)


class RecoilLoopTests(unittest.TestCase):
    def run_loop(self,held=False,visible=False,dead_at=None,focus_at=None,bad_at=None,weapon_profile=None):
        """Drive the real loop with synthetic memory/keys; no game or OS input."""
        state=SimpleNamespace(frame=0)
        class Event:
            def is_set(self):return state.frame>=4
            def wait(self,seconds):state.frame+=1;return self.is_set()
        fields={'m_iShotsFired':10,'m_pAimPunchServices':20,'m_predictableBaseAngle':30,
                'm_pWeaponServices':40,'m_hActiveWeapon':50,'m_vOldOrigin':60,'m_vecViewOffset':70,
                'm_AttributeManager':80,'m_Item':90,'m_iItemDefinitionIndex':100}
        angles=[0.,0.];writes=[]
        def read(a,n):
            if a==300:return struct.pack('<2f',*angles)
            if a==3030:return struct.pack('<2f',float('nan') if state.frame==bad_at else state.frame*.5,0)
            if a==1060:return struct.pack('<3f',0,0,0)
            if a==1070:return struct.pack('<3f',0,0,64)
            if a==400:return b'\0'*64
            if a==5270:return struct.pack('<H',9)
            raise AssertionError((a,n))
        def write(a,data):
            self.assertEqual(a,300)
            angles[:]=struct.unpack('<2f',data);writes.append((state.frame,tuple(angles)))
        geometry=SimpleNamespace(visible=lambda *a:visible)
        eng=SimpleNamespace(ready=True,pm=True,stop_event=Event(),client=0,
            off={'dwLocalPlayerPawn':100,'dwEntityList':200,'dwViewAngles':300,'dwViewMatrix':400},
            _f=lambda c,n:fields[n],_off_h=1,_off_ph=2,target_id=-1,p_cache={},sx=1920,sy=1080,
            read_longlong=lambda a:{100:1000,200:2000,1020:3000,1040:4000}[a],
            read_int=lambda a:(state.frame if a==1010 else 0 if state.frame==dead_at and a==1001 else 100),
            read_uint=lambda a:99,read_team=lambda a:2 if a==1000 else 3,
            read_bytes=read,write_bytes=write,is_game_foreground=lambda:state.frame!=focus_at,
            visibility=SimpleNamespace(snapshot=lambda:geometry),entity_from_index=lambda *a:5000,
            get_bones=lambda *a:{6:(200,0,64)},get_bone=lambda *a:(200,0,64),w2s=lambda *a:(960,540))
        cfg=SimpleNamespace(enabled=True,aim_key=17,flick_enabled=False,rcs_enabled=True,
            team_mode=1,awp_mode=False,target_bone=6,fov=120,aim_response='Akıcı takip',
            aim_settle_ms=150,aim_max_speed=720,rcs_scale=100,rcs_yaw_scale=100)
        if weapon_profile is not None:
            from settings_profiles import ProfileStore,WeaponRuntime
            eng.profiles=ProfileStore(None,cfg)
            eng.profiles.save_weapon('weapon:9',weapon_profile)
            eng.runtime_config=WeaponRuntime(cfg,eng.profiles)
        shim=SimpleNamespace(windll=SimpleNamespace(user32=SimpleNamespace(GetAsyncKeyState=lambda k:0x8000 if held else 0)))
        def roster(*a):eng.p_cache={1:(5000,6000,99)} if visible else {}
        with patch('focus_engine.ctypes',shim),patch('focus_engine.refresh_players',roster), \
             patch('focus_engine.time.monotonic',side_effect=lambda:1+state.frame/120), \
             patch('focus_engine.time.sleep'):
            aim_loop(eng,cfg)
        return writes

    def test_real_loop_uses_weapon_profile_without_changing_default_recoil(self):
        self.assertEqual(self.run_loop(weapon_profile={'rcs_scale':50}),
                         [(1,(-.5,0.)),(2,(-1.,0.)),(3,(-1.5,0.))])
        self.assertEqual(self.run_loop(weapon_profile={'rcs_enabled':False}),[])
        self.assertEqual(self.run_loop()[-1],(3,(-3.,0.)))

    def test_held_key_without_target_keeps_recoil_control(self):
        self.assertEqual(self.run_loop(held=True),self.run_loop(held=False))
        self.assertEqual(self.run_loop(held=True),[(1,(-1.,0.)),(2,(-2.,0.)),(3,(-3.,0.))])

    def test_visible_target_and_rcs_write_once_per_frame_without_smoothing_recoil(self):
        writes=self.run_loop(held=True,visible=True)
        self.assertEqual(len({f for f,_ in writes}),len(writes))
        self.assertEqual(writes[-1],(3,(-3.,0.)))

    def test_death_focus_loss_and_bad_sample_do_not_write_or_replay_correction(self):
        for key in ('dead_at','focus_at','bad_at'):
            writes=self.run_loop(**{key:2})
            self.assertEqual(writes,[(1,(-1.,0.))])


if __name__=='__main__':unittest.main()
