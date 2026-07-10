"""Status file writer (like OpenVPN's management interface)."""
import logging
import os
import time

logger = logging.getLogger("pyvpn.status")


class StatusFile:
    def __init__(self, path: str, interval: int = 10):
        self.path = path
        self.interval = interval
        self._start_time = time.time()
        self._last_write: float = 0
        self._bytes_in: int = 0
        self._bytes_out: int = 0
        self._packets_in: int = 0
        self._packets_out: int = 0

    def record_in(self, size: int) -> None:
        self._bytes_in += size
        self._packets_in += 1

    def record_out(self, size: int) -> None:
        self._bytes_out += size
        self._packets_out += 1

    def maybe_write(self, server_ip: str, virtual_ip: str | None, state: str, force: bool = False) -> None:
        now = time.time()
        if not force and now - self._last_write < self.interval:
            return
        self._last_write = now
        self._write(server_ip, virtual_ip, state)

    def _write(self, server_ip: str, virtual_ip: str | None, state: str) -> None:
        lines = [
            "OpenVPN CLIENT LIST",
            f"Updated,{time.strftime('%a %b %d %H:%M:%S %Y')}",
            "Common Name,Real Address,Bytes Received,Bytes Sent,Connected Since",
            f"CLIENT_ASSIGNED,{server_ip},{self._bytes_in},{self._bytes_out},{time.strftime('%a %b %d %H:%M:%S %Y', time.localtime(self._start_time))}",
            "ROUTING TABLE",
            f"{virtual_ip or 'N/A'},{server_ip},",
            "GLOBAL STATS",
            "Max bcast/mcast queue length,0",
            "END",
        ]
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                f.write("\n".join(lines) + "\n")
            os.replace(tmp, self.path)
        except OSError as e:
            logger.warning("Failed to write status file: %s", e)

    def close(self) -> None:
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
        except OSError:
            pass
