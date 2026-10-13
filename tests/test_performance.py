"""Resource regressions, using synthetic memory only (no game input or writes)."""
import ast
import ctypes
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from esp_visuals import BONE_IDS
from focus_engine import TargetScan
from targeting import TriggerPulse
from fire_control import FireControl

ROOT = Path(__file__).resolve().parents[1]


def definitions(*names, **namespace):
    tree = ast.parse((ROOT/'memory_bot.py').read_text(encoding='utf-8-sig'))
    nodes = [node for node in tree.body if getattr(node,'name',None) in names]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'memory_bot.py','exec'),namespace)
    return namespace


class PerformanceTests(unittest.TestCase):
    def test_team_read_ignores_nonzero_neighboring_fields(self):
        cls=definitions('CS2Engine')['CS2Engine']
        engine=object.__new__(cls)
        engine._off_t=20
        memory=b'\x03\xff\x80\x7f'
        engine.read_bytes=Mock(side_effect=lambda a,n:memory[:n])
        self.assertEqual(engine.read_team(1000),3)
        engine.read_bytes.assert_called_once_with(1020,1)

    def test_body_pose_uses_one_span_and_rejects_short_snapshot(self):
        cls = definitions('CS2Engine',struct=struct)['CS2Engine']
        engine = object.__new__(cls)
        engine._off_gsn, engine._off_ms = 10, 20
        engine.read_longlong = Mock(side_effect=[2000,3000])
        data = bytearray(28*32)
        for bone in BONE_IDS:
            struct.pack_into('<3f',data,bone*32,bone+1,bone+2,bone+3)
        engine.read_bytes = Mock(side_effect=lambda address,size:bytes(data[address-3000:address-3000+size]))
        result = engine.get_bones(1000,BONE_IDS)
        self.assertEqual(set(result),set(BONE_IDS))
        self.assertEqual(result[27],(28.,29.,30.))
        self.assertEqual(engine.read_bytes.call_count,1)
        engine.read_longlong.side_effect=[2000,3000]
        engine.read_bytes.side_effect=lambda a,n:b'\0'
        self.assertEqual(engine.get_bones(1000,BONE_IDS),{})

    def test_disabled_trigger_never_reads_target_or_presses_input(self):
        event = SimpleNamespace(is_set=Mock(side_effect=[False,True]),wait=Mock())
        current_target, mouse = Mock(), Mock()
        ns = definitions('trigger_worker',TriggerPulse=TriggerPulse,
                         Config=SimpleNamespace(enabled=True,trigger_enabled=False),
                         current_target=current_target,
                         ctypes=SimpleNamespace(windll=SimpleNamespace(user32=SimpleNamespace(mouse_event=mouse))))
        eng = SimpleNamespace(stop_event=event,fire_control=FireControl(mouse,mouse,mouse,mouse))
        ns['trigger_worker'](eng)
        current_target.assert_not_called()
        mouse.assert_not_called()
        self.assertFalse(eng.is_firing)
        self.assertGreaterEqual(event.wait.call_args.args[0],.02)

    def test_scan_budget_eventually_reaches_exposed_later_player(self):
        scanner = TargetScan()
        hidden = {bone:(20.,0.,4.) for bone in BONE_IDS}
        exposed = {6:(30.,8.,7.)}
        candidates = [((1,100,200,300,400),hidden),((2,101,201,301,401),exposed)]
        calls = []
        geometry = SimpleNamespace(visible=lambda eye,p:calls.append(p) or p[1]>5)
        selected = None
        for _ in range(20):
            before = len(calls)
            selected = scanner.choose(candidates,6,(0,0,4),lambda p:p[:2],geometry,
                                      (0,0),100,seconds=1,max_rays=3)
            self.assertLessEqual(len(calls)-before,3)
            if selected: break
        self.assertIsNotNone(selected)
        self.assertEqual(selected[0],2)

        geometry.visible=lambda eye,p:False
        self.assertIsNone(scanner.choose(candidates,6,(0,0,4),lambda p:p[:2],geometry,
                                         (0,0),100,locked=2,seconds=1,max_rays=100))

    def test_slow_raycast_yields_after_budget_and_offscreen_never_casts(self):
        scanner = TargetScan()
        geometry = SimpleNamespace(visible=Mock(return_value=False))
        candidate = [((1,100,200,300,400),{6:(20,0,7),4:(20,0,4)})]
        ticks=iter([0,.003])
        result=scanner.choose(candidate,6,(0,0,4),lambda p:p[:2],geometry,(0,0),100,
                              clock=lambda:next(ticks))
        self.assertIsNone(result)
        self.assertEqual(geometry.visible.call_count,1)
        geometry.visible.reset_mock()
        scanner.choose(candidate,6,(0,0,4),lambda p:(999,999),geometry,(0,0),100)
        geometry.visible.assert_not_called()

    def test_existing_clear_lock_wins_and_is_checked_again(self):
        candidates=[((1,100,200,300,400),{6:(20,0,7)}),((2,101,201,301,401),{6:(30,8,7)})]
        geometry=SimpleNamespace(visible=Mock(return_value=True))
        scan=TargetScan()
        for _ in range(2):
            result=scan.choose(candidates,6,(0,0,4),lambda p:p[:2],geometry,(0,0),100,locked=2)
            self.assertEqual(result[0],2)
        self.assertEqual(geometry.visible.call_count,2)


if __name__=='__main__':
    unittest.main()
