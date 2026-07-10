"""Windows TUN adapter using Wintun (WireGuard) driver.

Requires wintun.dll in PATH or current directory.
Download from: https://www.wintun.net/
"""
import ctypes
import ctypes.util
import logging
import os
import platform
import subprocess
import threading
from ctypes import wintypes

logger = logging.getLogger("pyvpn.tun_windows")

if platform.system() != "Windows":
    raise ImportError("Windows TUN is only available on Windows")


kernel32 = ctypes.windll.kernel32
ntdll = ctypes.windll.ntdll

WINTUN_ADAPTER_HANDLE = ctypes.c_void_p
WINTUN_SESSION_HANDLE = ctypes.c_void_p

_wintun = None
_functions = {}


def _load_wintun():
    global _wintun, _functions
    if _wintun is not None:
        return True

    paths = [
        "wintun.dll",
        os.path.join(os.path.dirname(__file__), "..", "wintun.dll"),
        os.path.join(os.environ.get("SYSTEMROOT", "C:\\Windows"), "wintun.dll"),
        os.path.join(os.environ.get("SYSTEMROOT", "C:\\Windows"), "System32", "wintun.dll"),
    ]

    dll_path = None
    for p in paths:
        if os.path.exists(p):
            dll_path = p
            break

    if not dll_path:
        logger.error("wintun.dll not found")
        return False

    _wintun = ctypes.WinDLL(dll_path)

    try:
        _functions["create_adapter"] = _wintun.WintunCreateAdapter
        _functions["create_adapter"].restype = WINTUN_ADAPTER_HANDLE
        _functions["create_adapter"].argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p]

        _functions["delete_adapter"] = _wintun.WintunDeleteAdapter
        _functions["delete_adapter"].restype = wintypes.BOOL
        _functions["delete_adapter"].argtypes = [WINTUN_ADAPTER_HANDLE, wintypes.BOOL, wintypes.BOOL]

        _functions["start_session"] = _wintun.WintunStartSession
        _functions["start_session"].restype = WINTUN_SESSION_HANDLE
        _functions["start_session"].argtypes = [WINTUN_ADAPTER_HANDLE, wintypes.DWORD]

        _functions["end_session"] = _wintun.WintunEndSession
        _functions["end_session"].restype = None
        _functions["end_session"].argtypes = [WINTUN_SESSION_HANDLE]

        _functions["get_read_wait_event"] = _wintun.WintunGetReadWaitEvent
        _functions["get_read_wait_event"].restype = wintypes.HANDLE
        _functions["get_read_wait_event"].argtypes = [WINTUN_SESSION_HANDLE]

        _functions["receive_packet"] = _wintun.WintunReceivePacket
        _functions["receive_packet"].restype = ctypes.c_void_p
        _functions["receive_packet"].argtypes = [WINTUN_SESSION_HANDLE, ctypes.POINTER(wintypes.DWORD)]

        _functions["release_receive_packet"] = _wintun.WintunReleaseReceivePacket
        _functions["release_receive_packet"].restype = None
        _functions["release_receive_packet"].argtypes = [WINTUN_SESSION_HANDLE, ctypes.c_void_p]

        _functions["allocate_send_packet"] = _wintun.WintunAllocateSendPacket
        _functions["allocate_send_packet"].restype = ctypes.c_void_p
        _functions["allocate_send_packet"].argtypes = [WINTUN_SESSION_HANDLE, wintypes.DWORD]

        _functions["send_packet"] = _wintun.WintunSendPacket
        _functions["send_packet"].restype = None
        _functions["send_packet"].argtypes = [WINTUN_SESSION_HANDLE, ctypes.c_void_p]

        return True
    except AttributeError as e:
        logger.error("Wintun function not found: %s", e)
        _wintun = None
        return False


def _guid_from_name(name: str):
    import hashlib
    h = hashlib.md5(name.encode()).digest()
    h = h[:16]
    h = bytearray(h)
    h[7] = (h[7] & 0x0f) | 0x40
    h[8] = (h[8] & 0x3f) | 0x80
    return bytes(h)


class TunInterface:
    def __init__(self, name: str = "tun0"):
        self.name = name
        self._adapter = None
        self._session = None
        self._read_event = None
        self._closed = False
        self._read_lock = threading.Lock()

    def open(self) -> None:
        if not _load_wintun():
            raise RuntimeError("Failed to load wintun.dll")

        logger.info("Creating Wintun adapter: %s", self.name)

        guid_bytes = _guid_from_name(self.name)
        guid_struct = (ctypes.c_ubyte * 16).from_buffer_copy(guid_bytes)

        adapter_name = f"pyvpn-{self.name}"
        self._adapter = _functions["create_adapter"](adapter_name, "Python VPN", guid_struct)
        if not self._adapter:
            error = kernel32.GetLastError()
            raise RuntimeError(f"Failed to create adapter: error {error}")
        logger.info("Adapter created")

        self._session = _functions["start_session"](self._adapter, 0x400000)
        if not self._session:
            error = kernel32.GetLastError()
            _functions["delete_adapter"](self._adapter, True, True)
            self._adapter = None
            raise RuntimeError(f"Failed to start session: error {error}")
        logger.info("Session started")

        self._read_event = _functions["get_read_wait_event"](self._session)

    def close(self) -> None:
        self._closed = True
        if self._session:
            _functions["end_session"](self._session)
            self._session = None
        if self._adapter:
            _functions["delete_adapter"](self._adapter, True, True)
            self._adapter = None

    def read(self, size: int = 65536) -> bytes:
        if not self._session:
            raise RuntimeError("TUN not open")

        while not self._closed:
            packet_size = wintypes.DWORD(0)
            packet_ptr = _functions["receive_packet"](self._session, ctypes.byref(packet_size))
            if packet_ptr and packet_size.value > 0:
                data = ctypes.string_at(packet_ptr, packet_size.value)
                _functions["release_receive_packet"](self._session, packet_ptr)
                return data

            kernel32.WaitForSingleObject(self._read_event, 100)

        raise OSError("TUN closed")

    def write(self, packet: bytes) -> int:
        if not self._session:
            raise RuntimeError("TUN not open")

        size = len(packet)
        packet_ptr = _functions["allocate_send_packet"](self._session, size)
        if not packet_ptr:
            return 0

        ctypes.memmove(packet_ptr, packet, size)
        _functions["send_packet"](self._session, packet_ptr)
        return size

    def set_ip(self, cidr: str) -> None:
        ip, prefix = cidr.split("/")
        adapter_name = f"pyvpn-{self.name}"
        subprocess.run(
            ["netsh", "interface", "ip", "set", "address",
             f"name={adapter_name}",
             f"source=static addr={ip} mask={prefixlen_to_netmask(int(prefix))}"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["netsh", "interface", "ip", "set", "interface",
             f"name={adapter_name}", "admin=enabled"],
            check=True, capture_output=True,
        )

    def set_mtu(self, mtu: int) -> None:
        adapter_name = f"pyvpn-{self.name}"
        subprocess.run(
            ["netsh", "interface", "ip", "set", "subinterface",
             f"name={adapter_name}", f"mtu={mtu}"],
            check=True, capture_output=True,
        )

    def fileno(self) -> int:
        raise NotImplementedError("fileno() not available on Windows TUN")

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()


def prefixlen_to_netmask(prefix: int) -> str:
    mask = (0xffffffff << (32 - prefix)) & 0xffffffff
    return ".".join(str((mask >> (8 * (3 - i))) & 0xff) for i in range(4))
