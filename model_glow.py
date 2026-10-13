"""Schema-resolved model highlighting with reversible field writes."""
import struct
import time


class ModelGlow:
    def __init__(self, read, write, field_offset, valid):
        self.read, self.write, self.valid = read, write, valid
        base = field_offset('C_BaseModelEntity', 'm_Glow')
        self.fields = {name: base + field_offset('CGlowProperty', name)
                       for name in ('m_iGlowType', 'm_glowColorOverride', 'm_bGlowing',
                                    'm_bFlashing', 'm_flGlowTime', 'm_flGlowStartTime')}
        self.saved = {}
        self.last_seen = {}
        self.start = min(self.fields.values())
        self.size = max(offset + (1 if name in ('m_bGlowing', 'm_bFlashing') else 4)
                        for name, offset in self.fields.items()) - self.start
        self.color_writes = {}
        self.repairs = {name:0 for name in self.fields}
        self.removals = 0
        self.effect_resets = 0
        self.last_overwrites = {}

    def apply(self, identity, color):
        valid = self.valid(identity)
        if valid is None:
            raise OSError('Glow identity temporarily unavailable')
        if valid is not True:
            return False
        pawn = identity[2]
        if color not in self.color_writes:
            rgb = bytes.fromhex(color.lstrip('#'))
            if len(rgb) != 3:
                raise ValueError('Glow color must be RGB')
            self.color_writes[color] = [('m_iGlowType', struct.pack('<i', 3)),
                      ('m_glowColorOverride', rgb + b'\xff'),
                      ('m_bFlashing', b'\x00'), ('m_flGlowTime', struct.pack('<f', 0)),
                      ('m_flGlowStartTime', struct.pack('<f', 0)), ('m_bGlowing', b'\x01')]
        writes = self.color_writes[color]
        # One read snapshots all six fields. Writes remain field-sized so adjacent
        # game-owned values are never overwritten by a stale full-struct copy.
        snapshot = self.read(pawn + self.start, self.size)
        if len(snapshot) != self.size:
            raise OSError('Incomplete glow snapshot')
        existing = identity in self.saved
        if existing and any(snapshot[self.fields[name]-self.start:self.fields[name]-self.start+len(data)] != data
                            for name,data in writes if name in ('m_iGlowType','m_glowColorOverride','m_bGlowing')):
            self.effect_resets += 1
        saved = self.saved.setdefault(identity, {})
        # Snapshot every affected field before the first write.
        for name, data in writes:
            address = pawn + self.fields[name]
            if address not in saved:
                offset = self.fields[name] - self.start
                saved[address] = (snapshot[offset:offset + len(data)], data)
        for name, data in writes:
            address = pawn + self.fields[name]
            original, _ = saved[address]
            offset = self.fields[name] - self.start
            if snapshot[offset:offset + len(data)] != data:
                self.write(address, data)
                if existing:
                    self.repairs[name] += 1
                    self.last_overwrites[name] = snapshot[offset:offset + len(data)].hex()
            saved[address] = original, data
        self.last_seen[identity] = time.monotonic()
        return True

    def restore_except(self, active=(), grace=0):
        for identity in list(self.saved.keys() - set(active)):
            if time.monotonic()-self.last_seen.get(identity,0) < grace:
                continue
            saved = self.saved[identity]
            valid = self.valid(identity)
            if valid is None:
                # A deleted/unreadable address must not retain its snapshot forever.

                if time.monotonic()-self.last_seen.get(identity,0) > 5:
                    del self.saved[identity]
                    self.last_seen.pop(identity,None)
                continue
            if valid:
                for address, (original, written) in list(saved.items()):

                    if self.read(address, len(original)) == written:
                        self.write(address, original)
                    del saved[address]
                self.removals += 1
            del self.saved[identity]
            self.last_seen.pop(identity,None)


class GlowMonitor:
    """Latch repeated engine contention; never oscillate between two renderers."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.started = None
        self.resets = 0
        self.peak_players = 0
        self.fallback = False

    def observe(self, resets, players, now):
        if self.fallback:
            return True
        if self.started is None:
            self.started = now
        self.resets += resets
        self.peak_players = max(self.peak_players, players)
        if now-self.started >= 2:
            self.fallback = self.resets >= max(12, self.peak_players*3)
            self.started, self.resets, self.peak_players = now, 0, 0
        return self.fallback
