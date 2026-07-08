import asyncio
import logging
import time
import ipaddress
from struct import unpack

from .config import Config
from .tun import TunInterface

logger = logging.getLogger("pyvpn.server")


class VpnServer:
    def __init__(self, config: Config):
        self.config = config
        self.tun: TunInterface | None = None
        self.transport: asyncio.DatagramTransport | None = None
        self.clients: dict[tuple, dict] = {}
        self.ip_to_addr: dict[str, tuple] = {}
        self._running = False

    @property
    def server_ip(self) -> str:
        if self.config.server:
            net = ipaddress.IPv4Network(self.config.server, strict=False)
            return f"{net.network_address + 1}/{net.prefixlen}"
        if self.config.ifconfig:
            return self.config.ifconfig
        return "10.8.0.1/24"

    async def run(self) -> None:
        logger.info("Server starting on port %d", self.config.port)
        logger.info("TUN IP: %s", self.server_ip)

        self.tun = TunInterface(self.config.dev)
        self.tun.open()
        self.tun.set_ip(self.server_ip)
        self.tun.set_mtu(1500)
        logger.info("TUN interface %s is up", self.config.dev)

        loop = asyncio.get_event_loop()

        transport, protocol = await loop.create_datagram_endpoint(
            lambda: ServerProtocol(self),
            local_addr=("0.0.0.0", self.config.port),
        )
        self.transport = transport

        loop.add_reader(self.tun.fileno(), self._on_tun_readable)

        self._running = True
        logger.info("Server is ready")

        try:
            while self._running:
                await asyncio.sleep(3600)
        except KeyboardInterrupt:
            self.stop()
        finally:
            loop.remove_reader(self.tun.fileno())
            self.tun.close()
            transport.close()
            logger.info("Server stopped")

    def stop(self) -> None:
        self._running = False

    def _on_tun_readable(self) -> None:
        try:
            packet = self.tun.read()
        except OSError:
            return

        if not packet or len(packet) < 20:
            return

        if not self.clients:
            return

        dest_ip = ip_from_ipv4_packet(packet)

        client_addr = self.ip_to_addr.get(dest_ip)
        if client_addr:
            self.transport.sendto(packet, client_addr)
        else:
            if self.config.verb >= 3:
                logger.debug("No client for IP %s, dropping %d bytes", dest_ip, len(packet))

    def register_client(self, addr: tuple) -> None:
        if addr not in self.clients:
            self.clients[addr] = {
                "addr": addr,
                "connected_at": time.time(),
                "virtual_ip": None,
            }
            logger.info("New client: %s", addr)

    def update_client_ip(self, addr: tuple, ip: str) -> None:
        old = self.clients.get(addr, {}).get("virtual_ip")
        if old and old in self.ip_to_addr:
            del self.ip_to_addr[old]
        if addr in self.clients:
            self.clients[addr]["virtual_ip"] = ip
        self.ip_to_addr[ip] = addr
        logger.info("Client %s mapped to IP %s", addr, ip)


class ServerProtocol(asyncio.DatagramProtocol):
    def __init__(self, server: VpnServer):
        self.server = server
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        self.server.register_client(addr)

        if len(data) >= 20:
            src_ip = ip_from_ipv4_packet(data)
            if src_ip and src_ip != "0.0.0.0":
                self.server.update_client_ip(addr, src_ip)

        try:
            self.server.tun.write(data)
        except OSError as e:
            logger.error("TUN write error: %s", e)

    def error_received(self, exc: Exception) -> None:
        logger.error("Socket error: %s", exc)


def ip_from_ipv4_packet(packet: bytes) -> str | None:
    if len(packet) < 20:
        return None
    version_ihl = packet[0]
    ihl = (version_ihl & 0x0f) * 4
    if len(packet) < ihl + 4:
        return None
    dest_bytes = packet[ihl + 4:ihl + 4 + 4] if len(packet) >= ihl + 8 else None
    if dest_bytes and len(dest_bytes) == 4:
        return ".".join(str(b) for b in dest_bytes)
    return None
