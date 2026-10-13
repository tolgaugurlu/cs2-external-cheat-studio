from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from control_panel import ControlPanel
from hotkeys import HotkeyEdges


class HotkeyTests(unittest.TestCase):
    def test_hold_toggles_once_and_release_allows_next_press(self):
        down=set()
        keys=HotkeyEdges(lambda key:0x8000 if key in down else 0)
        down.add(0x71)
        self.assertEqual(keys.poll(),[0x71])
        for _ in range(20): self.assertEqual(keys.poll(),[])
        down.clear()
        self.assertEqual(keys.poll(),[])
        down.add(0x71)
        self.assertEqual(keys.poll(),[0x71])

    def test_key_already_held_at_start_and_low_bit_do_not_toggle(self):
        state={0x71:0x8000,0x72:1}
        keys=HotkeyEdges(lambda key:state.get(key,0))
        self.assertEqual(keys.poll(),[])
        state.clear()
        keys.poll()
        state[0x71]=0x8000
        self.assertEqual(keys.poll(),[0x71])

    def test_f2_route_toggles_ready_panel_and_can_stop_if_readiness_lost(self):
        panel=object.__new__(ControlPanel)
        panel.closing=False
        panel.root=SimpleNamespace(after=Mock())
        panel.cfg=SimpleNamespace(enabled=False)
        panel.eng=SimpleNamespace(ready=True)
        panel.hotkey_edges=SimpleNamespace(poll=lambda:[0x71])
        panel.poll_hotkeys()
        self.assertTrue(panel.cfg.enabled)
        panel.eng.ready=False
        panel.poll_hotkeys()
        self.assertFalse(panel.cfg.enabled)
        self.assertEqual(panel.root.after.call_count,2)

    def test_start_during_validation_stays_inactive(self):
        panel=object.__new__(ControlPanel)
        panel.cfg=SimpleNamespace(enabled=False)
        panel.eng=SimpleNamespace(ready=False,loading=True,offset_status='Validating',fetch=Mock())
        panel.toggle()
        self.assertFalse(panel.cfg.enabled)
        panel.eng.fetch.assert_not_called()


if __name__=='__main__': unittest.main()
