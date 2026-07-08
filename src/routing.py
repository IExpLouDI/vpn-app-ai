import ipaddress
import threading
import logging

logger = logging.getLogger("pyvpn.routing")

POOL_LOCK = threading.Lock()


class IpPool:
    def __init__(self, subnet: str, pool_range: str | None = None):
        self.network = ipaddress.IPv4Network(subnet, strict=False)
        self.server_ip = str(self.network.network_address + 1)

        if pool_range and "-" in pool_range:
            start_str, end_str = pool_range.split("-")
            start = int(ipaddress.IPv4Address(start_str.strip()))
            end = int(ipaddress.IPv4Address(end_str.strip()))
        else:
            start = int(self.network.network_address + 2)
            end = int(self.network.broadcast_address - 1)

        self._available: set[int] = set(range(start, end + 1))
        self._allocated: dict[str, int] = {}
        self._allocated_by_int: dict[int, str] = {}

    def allocate(self, client_id: str) -> str | None:
        with POOL_LOCK:
            if not self._available:
                logger.warning("IP pool exhausted")
                return None
            ip_int = min(self._available)
            self._available.remove(ip_int)
            ip_str = str(ipaddress.IPv4Address(ip_int))
            self._allocated[client_id] = ip_int
            self._allocated_by_int[ip_int] = client_id
            logger.info("Assigned IP %s to %s", ip_str, client_id)
            return ip_str

    def release(self, client_id: str) -> None:
        with POOL_LOCK:
            ip_int = self._allocated.pop(client_id, None)
            if ip_int is not None:
                self._allocated_by_int.pop(ip_int, None)
                self._available.add(ip_int)
                logger.info("Released IP %s from %s",
                            str(ipaddress.IPv4Address(ip_int)), client_id)

    def allocated_count(self) -> int:
        return len(self._allocated)

    def allocated_ips(self) -> list[str]:
        return [str(ipaddress.IPv4Address(i)) for i in sorted(self._allocated_by_int)]

    def get_client_ip(self, client_id: str) -> str | None:
        ip_int = self._allocated.get(client_id)
        if ip_int is not None:
            return str(ipaddress.IPv4Address(ip_int))
        return None

    def get_client_id_by_ip(self, ip_str: str) -> str | None:
        ip_int = int(ipaddress.IPv4Address(ip_str))
        return self._allocated_by_int.get(ip_int)


def setup_nat(interface: str, tun_network: str) -> None:
    import subprocess
    logger.info("Setting up NAT on %s for %s", interface, tun_network)
    subprocess.run(
        ["iptables", "-t", "nat", "-C", "POSTROUTING",
         "-s", tun_network, "-o", interface, "-j", "MASQUERADE"],
        capture_output=True,
    )
    subprocess.run(
        ["iptables", "-t", "nat", "-A", "POSTROUTING",
         "-s", tun_network, "-o", interface, "-j", "MASQUERADE"],
        check=True, capture_output=True,
    )


def enable_ip_forward() -> None:
    import subprocess
    logger.info("Enabling IP forwarding")
    for proc in ("/proc/sys/net/ipv4/ip_forward",
                 "/proc/sys/net/ipv6/conf/all/forwarding"):
        try:
            with open(proc, "w") as f:
                f.write("1")
        except Exception:
            pass


def add_route(network: str, via: str | None = None, dev: str | None = None) -> None:
    import subprocess
    cmd = ["ip", "route", "add", network]
    if via:
        cmd += ["via", via]
    if dev:
        cmd += ["dev", dev]
    logger.info("Adding route: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode() if e.stderr else ""
        if "File exists" not in stderr:
            logger.warning("Route add failed: %s", stderr)


def delete_route(network: str, via: str | None = None, dev: str | None = None) -> None:
    import subprocess
    cmd = ["ip", "route", "delete", network]
    if via:
        cmd += ["via", via]
    if dev:
        cmd += ["dev", dev]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except Exception:
        pass


def push_route(client_ip: str, route: str, gateway: str, tun_dev: str) -> str | None:
    import subprocess
    cmd = ["ip", "route", "add", route, "via", gateway, "dev", tun_dev]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return None
    except subprocess.CalledProcessError as e:
        return e.stderr.decode() if e.stderr else "unknown error"
