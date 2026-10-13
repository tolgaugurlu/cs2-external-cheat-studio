import unittest
from types import SimpleNamespace

from targeting import current_target, TriggerPulse


class TargetTests(unittest.TestCase):
    def setUp(self):
        self.cfg = SimpleNamespace(enabled=True, team_mode=1, wall_lock_active=True,
                                   vis_check=False, glow_chams=True)
        self.memory = {101: 1000, 102: 2000, 1001: 100, 1002: 2, 1003: 8,
                       3001: 100, 3002: 3}
        self.engine = SimpleNamespace(ready=True, pm=True, client=100,
            off={'dwLocalPlayerPawn': 1, 'dwEntityList': 2},
            _off_h=1, _off_t=2, _off_id=3,
            read_longlong=lambda a: self.memory[a], read_int=lambda a: self.memory[a],
            read_team=lambda pawn:self.memory[pawn+2],
            entity_from_index=lambda el, index: 3000 if el == 2000 and index == 8 else 0,
            is_game_foreground=lambda: True)

    def test_fresh_live_target_and_expected_pawn_match(self):
        self.assertEqual(current_target(self.engine, self.cfg, 8, 3000), (8, 3000))
        self.assertIsNone(current_target(self.engine, self.cfg, 8, 9999))
        self.assertIsNone(current_target(self.engine, self.cfg, 9, 3000))

    def test_loss_of_crosshair_immediately_denies_previous_target(self):
        self.assertIsNotNone(current_target(self.engine, self.cfg))
        self.memory[1003] = 0

        self.assertIsNone(current_target(self.engine, self.cfg))

    def test_all_unknown_indexes_fail_closed(self):
        for value in (-1, 0, 32767, 4294967295):
            self.memory[1003] = value
            self.assertIsNone(current_target(self.engine, self.cfg))

    def test_death_team_filter_disable_and_focus_loss(self):
        for address, value in ((1001, 0), (3001, 0), (3002, 2)):
            old = self.memory[address]
            self.memory[address] = value
            self.assertIsNone(current_target(self.engine, self.cfg))
            self.memory[address] = old
        self.cfg.enabled = False
        self.assertIsNone(current_target(self.engine, self.cfg))
        self.cfg.enabled = True
        self.engine.is_game_foreground = lambda: False
        self.assertIsNone(current_target(self.engine, self.cfg))

    def test_team_only_filter_is_enforced(self):
        self.cfg.team_mode = 2
        self.assertIsNone(current_target(self.engine, self.cfg))
        self.memory[3002] = 2
        self.assertIsNotNone(current_target(self.engine, self.cfg))

    def test_read_failure_does_not_reuse_positive_result(self):
        self.assertIsNotNone(current_target(self.engine, self.cfg))
        def failed(address):
            raise OSError('simulated inaccessible memory')
        self.engine.read_int = failed
        self.assertIsNone(current_target(self.engine, self.cfg))


class PulseTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.pulse = TriggerPulse(lambda: self.events.append('down'), lambda: self.events.append('up'))

    def test_target_lost_during_delay_never_fires(self):
        self.pulse.update(0, (8, 3000), True, 'TAP', 100)
        self.pulse.update(.09, None, True, 'TAP', 100)
        self.pulse.update(.11, None, True, 'TAP', 100)
        self.assertEqual(self.events, [])

    def test_full_spray_releases_on_loss_or_disable(self):
        for enabled, target in ((True, None), (False, (8, 3000))):
            self.pulse.update(0, (8, 3000), True, 'SPRAY_FULL', 0)
            self.pulse.update(.001, target, enabled, 'SPRAY_FULL', 0)
            self.assertFalse(self.pulse.held)
        self.assertEqual(self.events, ['down', 'up', 'down', 'up'])

    def test_burst_does_not_send_remaining_shots_after_loss(self):
        self.pulse.update(0, (8, 3000), True, 'BURST', 0)
        self.pulse.update(.005, None, True, 'BURST', 0)
        for now in (.01, .09, .18, .5):
            self.pulse.update(now, None, True, 'BURST', 0)
        self.assertEqual(self.events, ['down', 'up'])

    def test_replaced_pawn_requires_new_delay(self):
        self.pulse.update(0, (8, 3000), True, 'TAP', 100)
        self.pulse.update(.1, (8, 4000), True, 'TAP', 100)
        self.assertEqual(self.events, [])
        self.pulse.update(.21, (8, 4000), True, 'TAP', 100)
        self.assertEqual(self.events, ['down'])
