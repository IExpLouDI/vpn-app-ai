import os
import struct
import subprocess
import platform

try:
    import fcntl
except ModuleNotFoundError:
    fcntl = None

TUNSETIFF = 0x400454ca
IFF_TUN = 0x0001
IFF_NO_PI = 0x1000

CLONE_DEVICE = "/dev/net/tun"


class TunInterface:
    def __init__(self, name: str = "tun0"):
        self.name = name
        self.fd = None

    def open(self) -> None:
        if fcntl is None:
            raise RuntimeError("TUN interface is not available on this platform (fcntl missing)")

        if not os.path.exists(CLONE_DEVICE):
            raise RuntimeError(f"TUN clone device not found at {CLONE_DEVICE}")

        self.fd = os.open(CLONE_DEVICE, os.O_RDWR)

        flags = IFF_TUN | IFF_NO_PI
        ifr = struct.pack("16sH", self.name.encode("utf-8"), flags)
        fcntl.ioctl(self.fd, TUNSETIFF, ifr, True)

    def close(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def read(self, size: int = 65536) -> bytes:
        if self.fd is None:
            raise RuntimeError("TUN device not open")
        return os.read(self.fd, size)

    def write(self, packet: bytes) -> int:
        if self.fd is None:
            raise RuntimeError("TUN device not open")
        return os.write(self.fd, packet)

    def set_ip(self, cidr: str) -> None:
        ip, prefix = cidr.split("/")
        mask = prefixlen_to_netmask(int(prefix))
        system = platform.system().lower()

        if system == "linux":
            subprocess.run(
                ["ip", "addr", "add", cidr, "dev", self.name],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["ip", "link", "set", self.name, "up"],
                check=True, capture_output=True,
            )
        else:
            raise RuntimeError(f"Unsupported platform: {system}")

    def set_mtu(self, mtu: int) -> None:
        system = platform.system().lower()
        if system == "linux":
            subprocess.run(
                ["ip", "link", "set", self.name, "mtu", str(mtu)],
                check=True, capture_output=True,
            )
        else:
            raise RuntimeError(f"Unsupported platform: {system}")

    def fileno(self) -> int:
        if self.fd is None:
            raise RuntimeError("TUN device not open")
        return self.fd

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()


def prefixlen_to_netmask(prefix: int) -> str:
    mask = (0xffffffff << (32 - prefix)) & 0xffffffff
    return ".".join(str((mask >> (8 * (3 - i))) & 0xff) for i in range(4))
