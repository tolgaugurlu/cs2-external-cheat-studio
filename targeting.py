"""Conservative target authorization; radar state is never a sight test.

Crosshair identification is an engine signal, NOT a geometric raycast. There
is deliberately no last-seen grace period or cached positive authorization.
"""


def team_allowed(mode, local_team, target_team):
    if local_team not in (2, 3) or target_team not in (2, 3):
        return False
    return (mode == 0 or (mode == 1 and target_team != local_team)
            or (mode == 2 and target_team == local_team))


def current_target(engine, config, expected_index=None, expected_pawn=None):
    """Read a fresh crosshair target; reject unknown, dead or replaced pawns."""
    try:
        if not (config.enabled and engine.ready and engine.pm
                and engine.is_game_foreground()):
            return None
        local = engine.read_longlong(engine.client + engine.off['dwLocalPlayerPawn'])
        if not local or engine.read_int(local + engine._off_h) <= 0:
            return None
        index = engine.read_int(local + engine._off_id)
        if not 0 < index < 0x7FFF or (expected_index is not None and index != expected_index):
            return None
        entity_list = engine.read_longlong(engine.client + engine.off['dwEntityList'])
        pawn = engine.entity_from_index(entity_list, index)
        if not pawn or pawn == local or (expected_pawn is not None and pawn != expected_pawn):
            return None
        if engine.read_int(pawn + engine._off_h) <= 0:
            return None
        if not team_allowed(config.team_mode, engine.read_team(local), engine.read_team(pawn)):
            return None
        return index, pawn
    except (OSError, ValueError, KeyError, TypeError):
        return None


class TriggerPulse:
    """Non-blocking fire control. Reauthorize throughout a hold and each burst."""

    def __init__(self, press, release):
        self.press, self.release = press, release
        self.held = False
        self.target = None
        self.due = 0.0
        self.up_at = 0.0
        self.burst_count = 0

    def cancel(self):
        if self.held:
            self.release()
        self.held = False
        self.target = None
        self.burst_count = 0

    def update(self, now, target, enabled, mode, delay_ms):
        if not enabled or target is None:
            self.cancel()
            return
        if target != self.target:
            self.cancel()
            self.target = target
            self.due = now + max(0, delay_ms) / 1000
        if self.held:
            if mode == 'SPRAY_FULL':
                return
            if now < self.up_at:
                return
            self.release()
            self.held = False
        if now < self.due:
            return
        self.press()
        self.held = True
        self.up_at = now + (0.02 if mode in ('SPRAY', 'LEGIT') else 0.01)
        interval = {'TAP': .26, 'SPRAY': .04, 'LEGIT': .14,
                    'AWP': .36, 'PISTOL_MACRO': .04}.get(mode, .09)
        if mode == 'BURST':
            self.burst_count += 1
            if self.burst_count == 3:
                interval = .24
                self.burst_count = 0
        self.due = now + max(interval, max(0, delay_ms) / 1000)
