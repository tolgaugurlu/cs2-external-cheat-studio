"""Time-based angular tracking with damped motion and bounded velocity feed-forward."""
import math


def angle_delta(target, current):
    return target[0]-current[0], (target[1]-current[1]+180)%360-180


def normalized(angles):
    return max(-89.,min(89.,angles[0])), (angles[1]+180)%360-180


class SmoothLock:
    def __init__(self):
        self.reset()

    def reset(self):
        self.identity = None
        self.previous_target = None
        self.previous_output = None
        self.velocity = (0.,0.)
        self.target_velocity = (0.,0.)

    def step(self, identity, current, desired, dt, settle_ms=90, max_speed=720):
        if not all(math.isfinite(v) for v in (*current,*desired,dt,settle_ms,max_speed)):
            self.reset()
            raise ValueError('Invalid angular sample')
        if dt <= 0:
            return normalized(current)
        if identity != self.identity or dt > .075:
            self.reset()
            self.identity = identity
        dt = min(dt,.05)
        desired = normalized(desired)
        max_speed = max(30.,min(1440.,max_speed))
        omega = 6/max(.04,min(.3,settle_ms/1000))
        if self.previous_output and math.hypot(*angle_delta(current,self.previous_output)) > 5:
            self.velocity = (0.,0.)
        if self.previous_target is not None:
            measured = tuple(max(-max_speed,min(max_speed,d/dt))
                             for d in angle_delta(desired,self.previous_target))
            alpha = -math.expm1(-dt/.035)
            self.target_velocity = tuple(v+(m-v)*alpha for v,m in zip(self.target_velocity,measured))
        error = angle_delta(desired,current)
        decay = math.exp(-omega*dt)
        steps, velocities = [], []
        for delta, velocity, target_velocity in zip(error,self.velocity,self.target_velocity):
            relative = velocity-target_velocity
            transient = (relative-omega*delta)*dt
            step = delta+target_velocity*dt+(-delta+transient)*decay
            next_velocity = target_velocity+(relative-omega*transient)*decay
            # Stay between the current view and the verified visible point.
            bounded = max(0.,min(delta,step)) if delta >= 0 else min(0.,max(delta,step))
            if abs(delta) < .004:
                bounded, next_velocity = delta, 0.
            elif bounded != step:
                next_velocity = 0.
            steps.append(bounded)
            velocities.append(next_velocity)
        length = math.hypot(*steps)
        if length > max_speed*dt:
            steps = [step*max_speed*dt/length for step in steps]
            velocities = [step/dt for step in steps]
        result = normalized((current[0]+steps[0],current[1]+steps[1]))
        self.previous_target, self.previous_output = desired, result
        self.velocity = tuple(velocities)
        return result
