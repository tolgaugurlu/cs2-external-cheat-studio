"""Sequence and real-loop tests use fake memory and callbacks, never OS input."""
from dataclasses import replace
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fire_control import FireControl
from flick_shot import FlickAbort, FlickShot, ShotSnapshot
from focus_engine import GameFlickPort, aim_loop


class FakePort:
    def __init__(self):
        self.cfg = SimpleNamespace(flick_enabled=True,flick_key=6,flick_knife_key=51)
        self.events, self.keys = [], set()
        self.fire = FireControl(lambda:self.events.append('down'),lambda:self.events.append('up'),
                                self.press_key,lambda k:self.events.append(('key_up',k)))
        self.value = ShotSnapshot((10,20,30),(-7,179),10,True)
        self.valid, self.clear, self.equipped, self.aimed = True,True,True,False
        self.selected = object()
        self.messages = []
        self.acquires = 0
        self.knife = False
        self.equip_works = True

    def press_key(self,key):
        self.events.append(('key_down',key))
        if key == 51 and self.equipped:self.knife = True
        if key == 81 and self.equip_works:self.knife = False

    def key_down(self,key): return key in self.keys
    def manual_fire_down(self): return 1 in self.keys
    def status(self,message): self.messages.append(message)
    def reset_scan(self): pass
    def clear_scan(self): pass
    def validate_player(self,original):
        if not self.valid: raise FlickAbort('inactive')
        if self.value.identity[0] != original.identity[0]:raise FlickAbort('player changed')
    def validate_saved_weapon(self,original):
        self.validate_player(original)
        if original.identity != self.value.identity:raise FlickAbort('weapon changed')
    def rearm_snapshot(self,original):
        self.validate_saved_weapon(original)
        return None if self.knife else self.snapshot()
    def snapshot(self):
        self.validate_player(self.value)
        if self.knife:raise FlickAbort('knife')
        return self.value
    def acquire(self,*args):
        self.acquires += 1
        return self.selected
    def align(self,snapshot,target):
        if not self.clear: raise FlickAbort('blocked')
        self.events.append('aim')
        previous,self.aimed = self.aimed,True
        return previous
    def restore(self,original):
        self.validate_player(original)
        if original.identity != self.value.identity: raise FlickAbort('changed')
        self.events.append(('restore',original.angles))
    def knife_equipped(self): return self.knife


class SequenceTests(unittest.TestCase):
    def setUp(self):
        self.port = FakePort()
        self.flick = FlickShot(self.port)
        self.flick.tick(0)

    def fire(self):
        self.port.keys.add(6)
        self.flick.tick(.01)
        self.assertNotIn('down',self.port.events)
        self.flick.tick(.02)

    def complete(self):
        self.port.value = replace(self.port.value,clip=9)
        for now in (.03,.05,.08,.09): self.flick.tick(now)

    def test_snap_fire_confirm_restore_knife_order_and_no_held_repeat(self):
        self.fire(); self.complete()
        self.assertEqual(self.port.events,['aim','aim','down','up',('restore',(-7,179)),
                                           ('key_down',51),('key_up',51)])
        for step in range(10,90): self.flick.tick(step/100)
        self.assertEqual(self.port.events.count('down'),1)
        self.assertTrue(self.port.fire.owner)
        self.port.keys.clear(); self.flick.tick(.9)
        self.assertFalse(self.port.fire.owner)
        self.port.keys.add(6); self.flick.tick(.91)
        self.assertEqual(self.port.events[-1],('key_down',81))
        self.flick.tick(.95)
        self.assertEqual(self.port.events.count('down'),2)

    def test_missing_shot_ack_releases_and_restores_without_knife_or_retry(self):
        self.fire()
        for now in (.05,.10,.15,.17): self.flick.tick(now)
        self.assertFalse(self.port.fire.held)
        self.assertIn(('restore',(-7,179)),self.port.events)
        self.assertEqual(self.port.events.count('down'),1)
        self.assertFalse(any(isinstance(e,tuple) and e[0]=='key_down' for e in self.port.events))

    def test_late_ammo_ack_after_mouse_release_still_completes(self):
        self.fire(); self.flick.tick(.05)
        self.assertEqual(self.flick.state,'confirm')
        self.port.value = replace(self.port.value,clip=9)
        self.flick.tick(.06)
        self.assertEqual(self.flick.state,'knife')
        self.assertIn(('restore',(-7,179)),self.port.events)

    def test_absent_target_times_out_without_moving_or_firing(self):
        self.port.selected = None
        self.port.keys.add(6)
        for now in (.01,.05,.1,.15,.18): self.flick.tick(now)
        self.assertEqual(self.port.events,[])
        self.assertEqual(self.flick.state,'cooldown')

    def test_target_is_fixed_during_sequence_and_cover_cancels(self):
        self.fire()
        self.port.clear = False
        self.flick.tick(.03)
        self.assertEqual(self.port.acquires,1)
        self.assertFalse(self.port.fire.held)
        self.assertNotIn(('key_down',51),self.port.events)

    def test_focus_loss_never_restores_or_presses_knife(self):
        self.fire(); self.port.valid = False
        self.flick.tick(.03)
        self.assertEqual(self.port.events,['aim','aim','down','up'])

    def test_weapon_switch_cancels_without_restoring_stale_view(self):
        self.fire()
        self.port.value = replace(self.port.value,identity=(10,99,999))
        self.flick.tick(.03)
        self.assertEqual(self.port.events,['aim','aim','down','up'])

    def test_empty_or_cooling_weapon_does_not_snap(self):
        for replacement in ({'clip':0},{'ready':False}):
            with self.subTest(replacement=replacement):
                self.setUp()
                self.port.value = replace(self.port.value,**replacement)
                self.port.keys.add(6); self.flick.tick(.01)
                self.assertEqual(self.port.events,[])

    def test_disabled_or_rebound_mid_click_releases_owned_input(self):
        for setting,value in (('flick_enabled',False),('flick_key',5)):
            with self.subTest(setting=setting):
                self.setUp(); self.fire()
                setattr(self.port.cfg,setting,value)
                self.flick.tick(.03)
                self.assertFalse(self.port.fire.held)
                self.assertFalse(self.port.fire.owner)
                self.assertEqual(self.port.events[-1],'up')

    def test_held_key_at_enable_requires_release(self):
        self.port.keys.add(6); self.flick.suspend()
        self.flick.tick(.01); self.flick.tick(.02)
        self.assertEqual(self.port.events,[])
        self.port.keys.clear(); self.flick.tick(.03)
        self.port.keys.add(6); self.flick.tick(.04)
        self.assertEqual(self.port.events,['aim'])

    def test_large_frame_gap_cancels_and_releases_click(self):
        self.fire(); self.flick.tick(.3)
        self.assertEqual(self.flick.state,'cooldown')
        self.assertFalse(self.port.fire.held)
        self.assertNotIn(('key_down',51),self.port.events)

    def test_manual_fire_is_not_combined_with_flick(self):
        self.port.keys.update((1,6)); self.flick.tick(.01)
        self.assertEqual(self.port.events,[])

    def test_knife_binding_failure_reported_after_key_release(self):
        self.port.equipped = False
        self.fire(); self.complete()
        for now in (.15,.2,.25,.31): self.flick.tick(now)
        self.assertFalse(self.port.fire.key)
        self.assertIn('eşleşmesini',self.port.messages[-1])

    def test_close_during_knife_press_releases_keyboard(self):
        self.fire(); self.port.value = replace(self.port.value,clip=9)
        self.flick.tick(.03); self.flick.tick(.05)
        self.assertEqual(self.port.fire.key,51)
        self.flick.suspend()
        self.assertEqual(self.port.events[-1],('key_up',51))

    def rearm(self):
        self.fire(); self.complete()
        self.port.keys.clear();self.flick.tick(.10)
        self.port.keys.add(6);self.flick.tick(.11)
        self.assertEqual(self.flick.state,'equip_hold')

    def test_repeat_rearms_then_waits_for_weapon_readiness_before_aim(self):
        self.rearm()
        self.port.value=replace(self.port.value,ready=False)
        before=list(self.port.events)
        for now in (.14,.2,.25,.3):self.flick.tick(now)
        self.assertEqual(self.port.events,before+[('key_up',81)])
        self.port.value=replace(self.port.value,ready=True,angles=(8,-24))
        self.flick.tick(.31)
        self.assertEqual(self.port.events.count('down'),2)
        self.port.value=replace(self.port.value,clip=8)
        self.flick.tick(.32)
        self.assertEqual(self.port.events[-1],('restore',(8,-24)))

    def test_failed_equip_times_out_without_aim_or_repeated_switch(self):
        self.port.equip_works=False
        self.rearm()
        before=self.port.events.count('aim')
        for frame in range(12,314):self.flick.tick(frame/100)
        self.assertEqual(self.port.events.count(('key_down',81)),1)
        self.assertEqual(self.port.events.count('down'),1)
        self.assertEqual(self.port.events.count('aim'),before)
        self.assertIsNone(self.port.fire.key)
        self.assertEqual(self.flick.state,'cooldown')

    def test_focus_loss_and_disable_while_drawing_release_weapon_key(self):
        for cause in ('focus','disable'):
            with self.subTest(cause=cause):
                self.setUp();self.rearm()
                if cause=='focus':self.port.valid=False
                else:self.port.cfg.flick_enabled=False
                self.flick.tick(.12)
                self.assertEqual(self.port.events[-1],('key_up',81))
                self.assertEqual(self.port.events.count('down'),1)

    def test_weapon_identity_change_during_deploy_aborts_without_shot(self):
        self.rearm()
        self.port.value=replace(self.port.value,identity=(10,21,31))
        self.flick.tick(.14)
        self.assertEqual(self.port.events.count('down'),1)
        self.assertEqual(self.flick.state,'cooldown')

    def test_no_remembered_weapon_on_initial_knife_press_does_not_guess(self):
        self.port.knife=True;self.port.keys.add(6)
        self.flick.tick(.01)
        self.assertEqual(self.port.events,[])
        self.assertIsNone(self.flick.last_weapon)

    def test_held_draw_key_and_colliding_bindings_do_not_send_input(self):
        self.fire();self.complete()
        self.port.keys={81};self.flick.tick(.10)
        before=list(self.port.events)
        self.port.keys.add(6);self.flick.tick(.11)
        self.assertEqual(self.port.events,before)
        self.port.cfg.flick_rearm_key=51
        self.flick.tick(.12)
        self.assertEqual(self.port.events,before)

    def test_suspend_preserves_remembered_weapon_but_revalidates_player(self):
        self.fire();self.complete();self.flick.suspend()
        self.assertIsNotNone(self.flick.last_weapon)
        self.port.value=replace(self.port.value,identity=(11,20,30))
        self.port.keys.clear();self.flick.tick(.10)
        self.port.keys.add(6);self.flick.tick(.11)
        self.assertNotIn(('key_down',81),self.port.events)


class InputOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.events=[]
        self.fire=FireControl(lambda:self.events.append('down'),lambda:self.events.append('up'),
                              lambda k:self.events.append(k),lambda k:self.events.append(-k))

    def test_trigger_hold_is_released_before_flick_and_cannot_steal_release(self):
        self.fire.update_trigger(1,'enemy',True,'SPRAY_FULL',0)
        self.fire.claim();self.fire.press()
        for now in (1.01,1.1,1.2):
            self.fire.update_trigger(now,'enemy',True,'TAP',0)
            self.fire.cancel_trigger()
        self.assertEqual(self.events,['down','up','down'])
        self.assertTrue(self.fire.held)
        self.fire.finish()
        self.assertEqual(self.events,['down','up','down','up'])

    def test_close_prevents_late_worker_input(self):
        self.fire.claim();self.fire.press();self.fire.press_key(51)
        self.fire.close();self.fire.claim();self.fire.press();self.fire.press_key(51)
        self.fire.update_trigger(1,'enemy',True,'TAP',0)
        self.assertEqual(self.events,['down',51,'up',-51])


class GameFixture:
    """Named synthetic schema fields and memory, with no external process."""
    def __init__(self):
        self.frame=0;self.keys=set();self.events=[];self.writes=[];self.memory={};self.fields={}
        self.focus=True;self.visible=True;self.ack=True
        self.cfg=SimpleNamespace(enabled=True,flick_enabled=True,flick_key=6,flick_knife_key=51,
            flick_fov=90,flick_bone=6,team_mode=1,aim_key=17,rcs_enabled=True,
            awp_mode=False,target_bone=6,fov=170,aim_response='Akıcı takip',aim_settle_ms=40,aim_max_speed=720)
        def f(cls,name):
            if (cls,name) not in self.fields:self.fields[cls,name]=len(self.fields)*10+100
            return self.fields[cls,name]
        self.f=f
        def field(base,cls,name,value):self.memory[base+f(cls,name)]=value
        self.field=field
        self.memory.update({1000:100000,2000:700000,3000:struct.pack('<2f',-3,20),
                            4000:b'\0'*64,5000:500000,100001:100,400001:100,600002:200,100003:200})
        field(100000,'C_BasePlayerPawn','m_pWeaponServices',200000)
        field(200000,'CPlayer_WeaponServices','m_hActiveWeapon',100)
        field(200000,'CCSPlayer_WeaponServices','m_flNextAttack',0.)
        self.definition=f('C_EconEntity','m_AttributeManager')+f('C_AttributeContainer','m_Item')+f('C_EconItemView','m_iItemDefinitionIndex')
        self.memory[300000+self.definition]=struct.pack('<H',9)
        self.memory[800000+self.definition]=struct.pack('<H',42)
        field(300000,'C_CSWeaponBase','m_bBurstMode',b'\0')
        field(300000,'C_BasePlayerWeapon','m_iClip1',10)
        field(300000,'C_BasePlayerWeapon','m_nNextPrimaryAttackTick',0)
        field(300000,'C_BasePlayerWeapon','m_flNextPrimaryAttackTickRatio',0.)
        field(300000,'C_CSWeaponBase','m_bInReload',b'\0')
        field(500000,'CBasePlayerController','m_nTickBase',64000)
        field(100000,'C_CSPlayerPawn','m_iShotsFired',0)
        field(100000,'C_CSPlayerPawn','m_pAimPunchServices',900000)
        field(900000,'CCSPlayer_AimPunchServices','m_predictableBaseAngle',struct.pack('<2f',0,0))
        field(100000,'C_BasePlayerPawn','m_vOldOrigin',struct.pack('<3f',0,0,0))
        field(100000,'C_BaseModelEntity','m_vecViewOffset',struct.pack('<3f',0,0,64))
        self.geometry=SimpleNamespace(visible=lambda *args:self.visible)
        self.eng=SimpleNamespace(ready=True,pm=True,client=0,_f=f,_off_h=1,_off_ph=2,_off_id=3,
            off={'dwLocalPlayerPawn':1000,'dwEntityList':2000,'dwViewAngles':3000,
                 'dwViewMatrix':4000,'dwLocalPlayerController':5000},
            stop_event=SimpleNamespace(is_set=lambda:False,wait=lambda t:False),
            is_game_foreground=lambda:self.focus,read_longlong=self.memory.__getitem__,
            read_uint=self.memory.__getitem__,read_int=self.memory.__getitem__,read_float=self.memory.__getitem__,
            read_bytes=lambda a,n:self.memory[a][:n],write_bytes=self.write,
            entity_from_index=lambda el,h:{100:300000,101:800000,200:400000}.get(h,0),
            read_team=lambda p:2 if p==100000 else 3,
            get_bones=lambda p,b:{6:(100,0,64)},get_bone=lambda p,b:(100,0,64),
            p_cache={1:(400000,600000,200)},target_id=-1,sx=1920,sy=1080,w2s=lambda *args:(960,540),
            visibility=SimpleNamespace(snapshot=lambda:self.geometry))
        self.eng.fire_control=FireControl(self.down,lambda:self.events.append('up'),
                                          self.knife,lambda k:self.events.append(('key_up',k)))
        self.port=GameFlickPort(self.eng,self.cfg)
        self.shim=SimpleNamespace(windll=SimpleNamespace(user32=SimpleNamespace(
            GetAsyncKeyState=lambda k:0x8000 if k in self.keys else 0)))

    def write(self,address,data):
        self.memory[address]=data
        self.writes.append((self.frame,struct.unpack('<2f',data)))
    def down(self):
        self.events.append('down')
        if self.ack:self.memory[300000+self.f('C_BasePlayerWeapon','m_iClip1')]-=1
    def knife(self,key):
        self.events.append(('key_down',key))
        if key==51:
            self.field(200000,'CPlayer_WeaponServices','m_hActiveWeapon',101)
        elif key==getattr(self.cfg,'flick_rearm_key',81):
            self.field(200000,'CPlayer_WeaponServices','m_hActiveWeapon',100)
            ticks=self.memory[500000+self.f('CBasePlayerController','m_nTickBase')]
            self.field(200000,'CCSPlayer_WeaponServices','m_flNextAttack',ticks/64+.25)


class GamePortTests(unittest.TestCase):
    def setUp(self):self.game=GameFixture()

    def test_snapshot_rejects_reload_burst_cooldown_and_unsupported_weapon(self):
        g=self.game
        self.assertTrue(g.port.snapshot().ready)
        g.field(300000,'C_CSWeaponBase','m_bInReload',b'\x01')
        self.assertFalse(g.port.snapshot().ready)
        g.field(300000,'C_CSWeaponBase','m_bInReload',b'\0')
        g.field(300000,'C_BasePlayerWeapon','m_nNextPrimaryAttackTick',64001)
        self.assertFalse(g.port.snapshot().ready)
        g.field(300000,'C_CSWeaponBase','m_bBurstMode',b'\x01')
        with self.assertRaises(FlickAbort):g.port.snapshot()
        g.memory[300000+g.definition]=struct.pack('<H',64)
        with self.assertRaises(FlickAbort):g.port.snapshot()

    def test_wall_map_and_identity_changes_fail_before_camera_write(self):
        for change in ('wall','map','handle','team','dead','focus'):
            with self.subTest(change=change):
                self.setUp();g=self.game
                g.port.reset_scan();snap=g.port.snapshot();target=g.port.acquire(snap,snap.angles)
                self.assertIsNotNone(target)
                if change=='wall':g.visible=False
                if change=='map':g.eng.visibility.snapshot=lambda:None
                if change=='handle':g.memory[600002]=201
                if change=='team':g.eng.read_team=lambda p:2
                if change=='dead':g.memory[400001]=0
                if change=='focus':g.focus=False
                with self.assertRaises(FlickAbort):g.port.align(snap,target)
                self.assertEqual(g.writes,[])

    def test_stale_crosshair_does_not_fire_before_actual_angle_matches(self):
        g=self.game;g.port.reset_scan();snap=g.port.snapshot()
        target=g.port.acquire(snap,snap.angles)
        self.assertFalse(g.port.align(snap,target))
        self.assertTrue(g.port.align(g.port.snapshot(),target))
        g.memory[100003]=201
        self.assertFalse(g.port.align(g.port.snapshot(),target))

    def test_all_direction_search_and_small_cone(self):
        g=self.game
        g.eng.get_bones=lambda p,b:{6:(-100,0,64)}
        snap=g.port.snapshot();g.port.reset_scan()
        self.assertIsNone(g.port.acquire(snap,(0,0)))
        g.cfg.flick_fov=180
        self.assertIsNotNone(g.port.acquire(snap,(0,0)))

    def test_moving_target_does_not_need_to_stop_for_angle_confirmation(self):
        g=self.game;g.port.reset_scan();snap=g.port.snapshot()
        target=g.port.acquire(snap,snap.angles)
        self.assertFalse(g.port.align(snap,target))
        g.eng.get_bone=lambda p,b:(100,3,64)
        self.assertTrue(g.port.align(g.port.snapshot(),target))
        self.assertGreater(g.writes[-1][1][1],1.)

    def test_full_real_aim_loop_restores_once_without_rcs_or_trigger_overwrite(self):
        g=self.game
        def wait(seconds):
            g.frame+=1
            g.keys={6,17} if g.frame else {17}
            # Race a trigger update against each sequence frame. Ownership must

            g.eng.fire_control.update_trigger(g.frame/120,'target',True,'TAP',0)
            return g.frame>=35
        g.eng.stop_event=SimpleNamespace(is_set=lambda:g.frame>=35,wait=wait)
        g.keys={17}

        original_update=g.eng.fire_control.update_trigger
        g.eng.fire_control.update_trigger=lambda now,target,*a:original_update(now,target if g.frame>1 else None,*a)
        with patch('focus_engine.ctypes',g.shim),patch('focus_engine.refresh_players'), \
             patch('focus_engine.time.monotonic',side_effect=lambda:1+g.frame/120), \
             patch('focus_engine.time.sleep'):
            aim_loop(g.eng,g.cfg)
        self.assertEqual(g.events.count('down'),1)
        self.assertIn(('key_down',51),g.events)
        self.assertIn(('key_up',51),g.events)

        self.assertEqual(g.writes[-1][1],g.writes[0][1])
        self.assertEqual(len({frame for frame,_ in g.writes}),len(g.writes))
        self.assertFalse(g.eng.fire_control.held)
        self.assertFalse(g.eng.fire_control.owner)
        self.assertIn('tamamlandı',g.eng.flick_status.lower())

    def test_real_port_repeats_gun_knife_cycle_and_respects_deployment_clock(self):
        g=self.game;flick=FlickShot(g.port)
        def tick(frame):
            g.frame=frame
            g.field(500000,'CBasePlayerController','m_nTickBase',64000+int(frame*64/120))
            return flick.tick(1+frame/120)
        with patch('focus_engine.ctypes',g.shim):
            tick(0);g.keys={6}
            for frame in range(1,18):tick(frame)
            self.assertTrue(g.port.knife_equipped())
            self.assertEqual(g.events.count('down'),1)
            g.keys.clear();tick(18)
            g.keys={6};tick(19)
            count=len(g.writes)
            for frame in range(20,49):tick(frame)
            self.assertEqual(len(g.writes),count)
            self.assertEqual(g.events.count('down'),1)
            for frame in range(49,120):tick(frame)
            self.assertEqual(g.events.count('down'),2)
            self.assertEqual(g.events.count(('key_down',81)),1)
            self.assertEqual(g.events.count(('key_up',81)),1)
            self.assertEqual(g.events.count(('key_down',51)),2)
            self.assertTrue(g.port.knife_equipped())
            self.assertEqual(g.writes[-1][1],(-3.,20.))
            self.assertFalse(g.eng.fire_control.held)
            self.assertIsNone(g.eng.fire_control.key)

    def test_rearm_never_accepts_a_different_gun_or_recycled_handle(self):
        g=self.game;saved=g.port.snapshot()
        g.field(200000,'CPlayer_WeaponServices','m_hActiveWeapon',101)
        self.assertIsNone(g.port.rearm_snapshot(saved))
        g.memory[800000+g.definition]=struct.pack('<H',7)
        with self.assertRaises(FlickAbort):g.port.rearm_snapshot(saved)
        g.eng.entity_from_index=lambda el,h:800000
        with self.assertRaises(FlickAbort):g.port.validate_saved_weapon(saved)


if __name__=='__main__':unittest.main()
