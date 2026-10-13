"""Bounded one-press sequence. This module never calls OS APIs itself."""
from dataclasses import dataclass


FLICK_KEYS = {'MOUSE5': 0x06, 'MOUSE4': 0x05, 'SHIFT': 0x10, 'ALT': 0x12, 'CTRL': 0x11}
KNIFE_KEYS = {key: ord(key) for key in ('3', '1', '2', '4', '5', 'Q', 'F', 'G', 'V', 'X', 'C', 'Z')}
REARM_KEYS = {key: ord(key) for key in ('Q', '1', '2', 'F', 'G', 'V', 'X', 'C', 'Z')}


class FlickAbort(Exception):
    pass


@dataclass(frozen=True)
class ShotSnapshot:
    identity: tuple
    angles: tuple
    clip: int
    ready: bool
    punch: tuple = (0., 0.)


class FlickShot:
    """A new release/press is required after completion, cancellation or enable."""
    def __init__(self, port):
        self.port = port
        self.down = None
        self.binding = None
        self.state = 'idle'
        self.start = None
        self.target = None
        self.moved = False
        self.shot = False
        self.deadline = 0.
        self.last_tick = None
        self.last_weapon = None

    def suspend(self):
        self.port.fire.finish()
        self.port.clear_scan()
        self.state = 'idle'
        self.down = self.binding = self.last_tick = None
        self.start = self.target = None

    def finish(self, now, message, cooldown=.15):
        self.port.fire.release()
        self.port.fire.release_key()
        self.port.status(message)
        self.state, self.deadline = 'cooldown', now + cooldown
        self.target = None
        self.port.clear_scan()

    def abort(self, now, reason, restore=True):
        self.port.fire.release()
        self.port.fire.release_key()
        # Restoration also revalidates the original live shooter/weapon. Never

        if restore and self.moved and self.start is not None:
            try:
                self.port.restore(self.start)
            except (FlickAbort, OSError, ValueError):
                pass
        self.finish(now, reason)

    def tick(self, now):
        cfg = self.port.cfg
        if not cfg.flick_enabled:
            if self.state != 'idle' or self.down is not None:
                self.suspend()
            return False
        key = getattr(cfg, 'flick_key', 6)
        knife = getattr(cfg, 'flick_knife_key', 0x33)
        rearm = getattr(cfg, 'flick_rearm_key', 0x51)
        if (key not in FLICK_KEYS.values() or knife not in KNIFE_KEYS.values()
                or rearm not in REARM_KEYS.values() or len({key,knife,rearm}) != 3):
            self.suspend()
            self.port.status('Geçerli ve farklı tuşlar seç')
            return False
        down = self.port.key_down(key)
        if self.binding != (key, knife, rearm):
            self.suspend()
            self.binding = (key, knife, rearm)
            self.down = down
            return False
        rising = down and not self.down
        self.down = down
        previous, self.last_tick = self.last_tick, now
        if self.state == 'cooldown':
            if now >= self.deadline and (not down or rising):
                self.port.fire.finish()
                self.state = 'idle'
                self.start = None
                if not rising:
                    return True
            else:
                return True
        if self.state == 'idle' and not rising:
            return False
        try:
            if self.state == 'idle':
                self.moved = self.shot = False
                self.start = None
                self.target = None


                if self.port.manual_fire_down():
                    raise FlickAbort('Önce sol fare tuşunu bırak')
                self.port.fire.claim()
                if self.port.knife_equipped():
                    if self.last_weapon is None:
                        raise FlickAbort('İlk flick için ateşli silahını seç')
                    self.port.validate_saved_weapon(self.last_weapon)
                    if self.port.key_down(rearm):
                        raise FlickAbort('Önce silaha dönüş tuşunu bırak')
                    self.port.fire.press_key(rearm)
                    self.state, self.deadline = 'equip_hold', now + .025
                    self.equip_until = now + 3.
                    self.port.status('Önceki silah çekiliyor · hazır olması bekleniyor')
                    return True
                self.start = self.port.snapshot()
                if self.start.clip <= 0 or not self.start.ready:
                    raise FlickAbort('Silah atışa hazır değil')
                self.port.reset_scan()
                self.state, self.deadline = 'acquire', now + .16
                self.port.status('Görünür hedef aranıyor')
            elif previous is not None and now - previous > .10:
                raise FlickAbort('Geciken işlem iptal edildi')

            if self.state in ('equip_hold','equip_wait'):
                self.port.validate_player(self.last_weapon)
                if now >= self.equip_until:
                    raise FlickAbort('Silah hazır olmadı · önceki silah tuşunu kontrol et')
                if self.state == 'equip_hold':
                    if now < self.deadline:
                        return True
                    self.port.fire.release_key()
                    self.state = 'equip_wait'
                snapshot = self.port.rearm_snapshot(self.last_weapon)
                if snapshot is None:
                    return True
                if snapshot.clip <= 0:
                    raise FlickAbort('Şarjör boş · silahı doldur')
                if not snapshot.ready:
                    return True


                self.start = snapshot
                self.port.reset_scan()
                self.state, self.deadline = 'acquire', now + .16
                self.port.status('Silah hazır · görünür hedef aranıyor')

            if self.state == 'knife_hold':
                self.port.validate_player(self.start)
                if now >= self.deadline:
                    self.port.fire.release_key()
                    self.state, self.deadline = 'knife_confirm', now + .22
                return True

            if self.state == 'knife_confirm':
                self.port.validate_player(self.start)
                if self.port.knife_equipped():
                    self.finish(now, 'Tamamlandı · tekrar basınca silah otomatik çekilir', cooldown=0.)
                elif now >= self.deadline:
                    self.finish(now, 'Atış yapıldı · bıçak tuşu eşleşmesini kontrol et')
                return True

            snapshot = self.port.snapshot()
            if snapshot.identity != self.start.identity:
                raise FlickAbort('Silah / oyuncu değişti')

            if self.state == 'acquire':
                self.target = self.port.acquire(snapshot, self.start.angles)
                if self.target is None:
                    if now >= self.deadline:
                        raise FlickAbort('Arama açısında görünür hedef yok')
                    return True
                self.state, self.deadline = 'align', now + .18

            if self.state == 'align':
                if now >= self.deadline or not snapshot.ready or snapshot.clip <= 0:
                    raise FlickAbort('Nişan / silah doğrulanamadı')

                # identity check. Confirmation examines the PRE-write angle;
                # a stale crosshair ID alone cannot authorize the shot.
                aligned = self.port.align(snapshot, self.target)
                self.moved = True
                if aligned:
                    self.before_clip = snapshot.clip
                    self.port.fire.press()
                    self.state, self.deadline = 'firing', now + .026
                    self.confirm_until = now + .14
                    self.port.status('Tek atış doğrulanıyor')
                return True

            if self.state in ('firing', 'confirm'):

                # or kill guarantee. Never pull the knife on mere mouse-down.
                if snapshot.clip < self.before_clip:
                    self.shot = True
                    self.last_weapon = self.start
                    self.port.fire.release()
                    self.port.restore(self.start)
                    self.moved = False
                    self.state, self.deadline = 'knife', now + .016
                    return True
                if self.state == 'firing':
                    if now >= self.deadline:
                        self.port.fire.release()
                        self.state = 'confirm'
                    else:
                        self.port.align(snapshot, self.target)
                if now >= self.confirm_until:
                    raise FlickAbort('Atış doğrulanmadı · tekrar ateşlenmedi')
                return True

            if self.state == 'knife' and now >= self.deadline:
                if self.port.key_down(knife):
                    raise FlickAbort('Atış yapıldı · bıçak tuşu zaten basılı')
                self.port.fire.press_key(knife)
                self.state, self.deadline = 'knife_hold', now + .025
            return True
        except (FlickAbort, OSError, ValueError) as error:
            self.abort(now, str(error))
            return True
