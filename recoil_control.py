"""Validated recoil deltas with explicit burst/weapon/focus lifecycle."""
import math


class RecoilControl:
    def __init__(self):
        self.reset()

    def reset(self):
        self.identity = None
        self.previous = (0., 0.)
        self.shots = 0
        self.time = None
        self.gains = None

    def sample(self, identity, shots, punch, now, pitch_percent=100, yaw_percent=100):
        """Return (absolute correction, incremental correction), in degrees.

        Observe the idle zero before compensating the first shot. Attaching in
        the middle of a burst establishes a baseline; it never catches up with
        accumulated recoil in one camera jump. No old delta crosses a reset.
        """
        if (not all(math.isfinite(v) for v in (*punch, now, pitch_percent, yaw_percent))
                or any(abs(v) >= 30 for v in punch) or not 0 <= shots <= 1000):
            self.reset()
            raise ValueError('Invalid recoil sample')
        gains = tuple(max(0., min(150., v)) / 50 for v in (pitch_percent, yaw_percent))
        offset = tuple(punch[i] * gains[i] for i in range(2)) if shots else (0., 0.)
        continuous = (identity == self.identity and self.time is not None
                      and 0 < now - self.time <= .1 and shots >= self.shots
                      and gains == self.gains)
        delta = tuple(offset[i] - self.previous[i] for i in range(2)) if shots and continuous else (0., 0.)
        # A corrupt finite sample must not turn the camera several dozen degrees.

        if continuous and shots and math.hypot(*delta) > 8:
            self.reset()
            raise ValueError('Discontinuous recoil sample')
        self.identity, self.previous, self.shots = identity, offset, shots
        self.time, self.gains = now, gains
        return offset, delta
