import logging

logger = logging.getLogger("pyvpn.protocol.replay")

MAX_WINDOW = 64


class ReplayWindow:
    def __init__(self, window_size: int = 64):
        if window_size < 1 or window_size > MAX_WINDOW:
            raise ValueError(f"window_size must be in [1, {MAX_WINDOW}], got {window_size}")
        self.window_size = window_size
        self._highest = -1
        self._seen = 0

    def check(self, packet_id: int) -> bool:
        if packet_id < 0:
            return False

        if self._highest == -1:
            self._highest = packet_id
            self._seen = 1
            return True

        if packet_id > self._highest:
            delta = packet_id - self._highest
            if delta >= self.window_size:
                self._seen = 0
            else:
                self._seen <<= delta
            self._seen |= 1
            self._highest = packet_id
            return True

        delta = self._highest - packet_id
        if delta >= self.window_size:
            return False
        if self._seen & (1 << delta):
            return False
        self._seen |= (1 << delta)
        return True

    def reset(self) -> None:
        self._highest = -1
        self._seen = 0
