"""Visual team/camera context, including death and spectator pawn transitions."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ViewContext:
    local: int
    team: int
    camera_pawn: int
    observed: int = 0

    def excludes(self, pawn):
        return pawn == self.local or pawn == self.observed


def view_context(engine, entity_list):
    local = engine.read_longlong(engine.client + engine.off['dwLocalPlayerPawn'])
    controller = engine.read_longlong(engine.client + engine.off['dwLocalPlayerController'])
    team = engine.read_team(controller) if controller else 0
    if team not in (2,3) and local:
        team = engine.read_team(local)
    camera = local
    observed = 0
    if not local or engine.read_int(local + engine._off_h) <= 0:
        try:
            if controller:
                handle = engine.read_uint(controller + engine._f('CCSPlayerController','m_hObserverPawn'))
                camera = engine.entity_from_index(entity_list,handle) or local
            if camera:
                services = engine.read_longlong(camera + engine._f('C_BasePlayerPawn','m_pObserverServices'))
                if services:
                    handle = engine.read_uint(services + engine._f('CPlayer_ObserverServices','m_hObserverTarget'))
                    target = engine.entity_from_index(entity_list,handle)
                    if target and engine.read_int(target + engine._off_h) > 0:
                        camera = observed = target
                        if team not in (2,3):
                            team = engine.read_team(target)
        except (OSError,KeyError,ValueError,RuntimeError):

            camera = 0
    if team not in (2,3):
        return None
    return ViewContext(local,team,camera,observed)
