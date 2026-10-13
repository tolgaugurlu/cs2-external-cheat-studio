"""Edge-triggered function keys without a low-level keyboard hook."""


class HotkeyEdges:
    KEYS = (0x71, 0x72, 0x73)

    def __init__(self, read_state):
        self.read_state = read_state

        self.down = {key for key in self.KEYS if read_state(key) & 0x8000}

    def poll(self):
        down = {key for key in self.KEYS if self.read_state(key) & 0x8000}
        pressed = [key for key in self.KEYS if key in down and key not in self.down]
        self.down = down
        return pressed
