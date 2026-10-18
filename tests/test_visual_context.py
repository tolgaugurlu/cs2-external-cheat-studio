import ast
from pathlib import Path
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from focus_engine import aim_loop
from targeting import team_allowed
from visual_context import ViewContext, view_context


class ViewerTests(unittest.TestCase):
    def setUp(self):
        self.memory={101:1000,102:2000,1001:100,1002:2,2002:2,
                     2040:90,3050:5000,5060:91,4001:100,4002:3}
        self.eng=SimpleNamespace(client=100,_off_h=1,
            off={'dwLocalPlayerPawn':1,'dwLocalPlayerController':2},
            read_longlong=lambda a:self.memory.get(a,0),read_uint=lambda a:self.memory.get(a,0),
            read_int=lambda a:self.memory[a],read_team=lambda p:self.memory.get(p+2,0),
            _f=lambda c,f:{'m_hObserverPawn':40,'m_pObserverServices':50,'m_hObserverTarget':60}[f],
            entity_from_index=lambda el,h:{90:3000,91:4000}.get(h,0))

    def test_alive_view_uses_own_pawn(self):
        self.assertEqual(view_context(self.eng,6000),ViewContext(1000,2,1000))

    def test_death_keeps_own_team_and_follows_observer_camera(self):
        self.memory[1001]=0
        context=view_context(self.eng,6000)
        self.assertEqual(context,ViewContext(1000,2,4000,4000))
        self.assertTrue(context.excludes(4000))
        self.assertFalse(context.excludes(9999))
        self.assertTrue(team_allowed(1,context.team,3))

    def test_destroyed_local_pawn_can_still_show_opponents(self):
        self.memory[101]=0
        self.assertEqual(view_context(self.eng,6000),ViewContext(0,2,4000,4000))

    def test_spectator_team_is_based_on_observed_player_if_own_team_unknown(self):
        self.memory.update({1001:0,1002:0,2002:1})
        self.assertEqual(view_context(self.eng,6000).team,3)

    def test_camera_switch_read_gap_does_not_erase_known_team(self):
        self.memory[1001]=0
        self.eng.read_uint=Mock(side_effect=OSError('switching camera'))
        self.assertEqual(view_context(self.eng,6000),ViewContext(1000,2,0))

    def test_unknown_team_is_not_invented(self):
        self.memory.update({1002:0,2002:0})
        self.assertIsNone(view_context(self.eng,6000))

    def test_dead_player_roster_refreshes_without_aim_or_recoil_writes(self):
        event=SimpleNamespace(stopped=False)
        event.is_set=lambda:event.stopped
        event.wait=lambda seconds:setattr(event,'stopped',True)
        eng=SimpleNamespace(ready=True,pm=True,client=100,stop_event=event,_off_h=1,
            _f=lambda c,f:0,off={'dwLocalPlayerPawn':1,'dwEntityList':2},
            read_longlong=lambda a:{101:1000,102:2000}[a],read_int=lambda a:0,
            is_game_foreground=lambda:True,target_id=5,old_punch=(1,1),write_bytes=Mock())
        with patch('focus_engine.refresh_players') as refresh:
            aim_loop(eng,SimpleNamespace(enabled=True))
        refresh.assert_called_once_with(eng,1000,2000)
        eng.write_bytes.assert_not_called()
        self.assertEqual(eng.target_id,-1)


class GlowLifecycleTests(unittest.TestCase):
    def test_focus_and_read_gaps_do_not_remove_then_reapply_silhouette(self):
        event=SimpleNamespace(frame=0)
        event.is_set=lambda:event.frame>=4
        event.wait=lambda seconds:setattr(event,'frame',event.frame+1)
        calls=[]
        class Glow:
            def __init__(self,*args):
                self.saved={};self.repairs={};self.removals=0
                self.effect_resets=0;self.last_overwrites={}
            def apply(self,identity,color):
                self.saved[identity]={}
                return True
            def restore_except(self,active=(),grace=0):
                calls.append((event.frame,set(active),grace))
            def interval(self):return 1/60
        def health(address):
            if event.frame==2: raise OSError('incomplete frame')
            return 100
        eng=SimpleNamespace(ready=True,pm=True,client=100,stop_event=event,_off_t=2,_off_h=1,_off_ph=3,
            off={'dwEntityList':1},p_cache={1:(3000,2000,7)},
            read_longlong=lambda a:5000,read_uint=lambda a:7,read_team=lambda p:3,read_int=health,
            read_bytes=Mock(),write_bytes=Mock(),_f=Mock(),is_game_foreground=lambda:event.frame!=1)
        cfg=SimpleNamespace(enabled=True,glow_chams=True,team_mode=1,esp_palette='palette')
        path=Path(__file__).resolve().parents[1]/'memory_bot.py'
        tree=ast.parse(path.read_text(encoding='utf-8-sig'))
        node=next(n for n in tree.body if getattr(n,'name',None)=='glow_worker')
        ns={'Config':cfg,'ModelGlow':Glow,'time':time,'PALETTES':{'palette':('red','blue'),'Koral / Mavi':('red','blue')},
            'team_allowed':team_allowed,'view_context':lambda *a:ViewContext(1000,2,1000),
            'wait_contour_frame':lambda stop,started,interval:stop.wait(interval)}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'memory_bot.py','exec'),ns)
        ns['glow_worker'](eng)
        identity=(2000,7,3000)
        self.assertEqual(calls,[(0,{identity},.75),(2,{identity},.75),(3,{identity},.75),(4,set(),0)])


if __name__=='__main__': unittest.main()
