"""Serialize trigger and one-shot input ownership across the two workers."""
import threading

from targeting import TriggerPulse


class FireControl:
    def __init__(self, down, up, key_down, key_up):
        self.lock = threading.RLock()
        self.down, self.up = down, up
        self.key_down, self.key_up = key_down, key_up
        self.trigger = TriggerPulse(down, up)
        self.owner = False
        self.held = False
        self.key = None
        self.closed = False

    def update_trigger(self, now, target, enabled, mode, delay):
        with self.lock:
            self.trigger.update(now, target, enabled and not self.owner and not self.closed, mode, delay)
            return self.trigger.held

    def cancel_trigger(self):
        with self.lock:
            self.trigger.cancel()

    def claim(self):
        with self.lock:
            self.trigger.cancel()
            self.owner = not self.closed

    def press(self):
        with self.lock:
            if self.owner and not self.closed and not self.held:
                self.held = True
                self.down()

    def release(self):
        with self.lock:
            if self.held:
                self.up()
                self.held = False

    def press_key(self, key):
        with self.lock:
            if self.owner and not self.closed and self.key is None:
                self.key = key
                self.key_down(key)

    def release_key(self):
        with self.lock:
            if self.key is not None:
                self.key_up(self.key)
                self.key = None

    def finish(self):
        with self.lock:
            try:
                self.release()
            finally:
                try:
                    self.release_key()
                finally:
                    self.owner = False

    def close(self):
        with self.lock:
            self.closed = True
            try:
                self.cancel_trigger()
            finally:
                self.finish()
