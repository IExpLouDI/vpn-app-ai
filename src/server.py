import asyncio
import logging
import time
import ipaddress
from struct import unpack

from .config import Config
from .tun import TunInterface
from .protocol.messages import Opcode, MessageType
from .protocol.packet import decode_packet
from .protocol.control import (
    Session, server_handle_reset, server_handle_client_hello,
    server_handle_client_finished,
)
from .protocol.data import DataChannel

logger = logging.getLogger("pyvpn.server")

CONTROL_HANDLERS = {
    MessageType.CLIENT_HELLO: server_handle_client_hello,
    MessageType.CLIENT_FINISHED: server_handle_client_finished,
}


class ClientSession:
    def __init__(self, addr: tuple, session: Session):
        self.addr = addr
        self.session = session
        self.data: DataChannel | None = None
        self.virtual_ip: str | None = None
        self.last_seen: float = time.time()

    @property
    def is_ready(self) -> bool:
        return self.session.is_established and self.data is not None


class VpnServer:
    def __init__(self, config: Config):
        self.config = config
        self.tun: TunInterface | None = None
        self.transport: asyncio.DatagramTransport | None = None
        self.clients: dict[tuple, ClientSession] = {}
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

        loop = asyncio.get_event_loop()

        transport, protocol = await loop.create_datagram_endpoint(
            lambda: ServerProtocol(self),
            local_addr=("0.0.0.0", self.config.port),
        )
        self.transport = transport
        loop.add_reader(self.tun.fileno(), self._on_tun_readable)

        self._running = True
        logger.info("Server ready on port %d", self.config.port)

        try:
            while self._running:
                self._cleanup_stale()
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            self.stop()
        finally:
            loop.remove_reader(self.tun.fileno())
            self.tun.close()
            transport.close()

    def stop(self) -> None:
        self._running = False

    def _cleanup_stale(self) -> None:
        now = time.time()
        stale = [a for a, c in self.clients.items()
                 if not c.session.is_established and
                 c.session.is_expired()]
        for addr in stale:
            logger.info("Removing stale session: %s", addr)
            cs = self.clients.pop(addr, None)
            if cs and cs.virtual_ip and cs.virtual_ip in self.ip_to_addr:
                del self.ip_to_addr[cs.virtual_ip]

    def _on_tun_readable(self) -> None:
        try:
            packet = self.tun.read()
        except OSError:
            return
        if not packet or len(packet) < 20:
            return

        dest_ip = _ipv4_dest(packet)
        if not dest_ip:
            return

        client_addr = self.ip_to_addr.get(dest_ip)
        if not client_addr:
            return

        cs = self.clients.get(client_addr)
        if not cs or not cs.is_ready:
            return

        wire = cs.data.encrypt(packet)
        self.transport.sendto(wire, client_addr)

    def _get_or_create_session(self, addr: tuple) -> ClientSession:
        if addr in self.clients:
            return self.clients[addr]
        session = Session(is_server=True)
        if self.config.ca and self.config.cert and self.config.key:
            session.configure(self.config.ca, self.config.cert, self.config.key)
        cs = ClientSession(addr, session)
        self.clients[addr] = cs
        return cs

    def handle_udp_data(self, data: bytes, addr: tuple) -> None:
        if len(data) < 1:
            return

        opcode_val = data[0]

        if opcode_val in (Opcode.HARD_RESET_CLIENT, Opcode.HARD_RESET_SERVER):
            cs = self._get_or_create_session(addr)
            packets = server_handle_reset(cs.session, data)
            for p in packets:
                self.transport.sendto(p, addr)
            return

        cs = self.clients.get(addr)
        if not cs:
            return

        cs.last_seen = time.time()

        if opcode_val == Opcode.CONTROL:
            try:
                _, _, payload = decode_packet(data)
            except (ValueError, IndexError):
                return

            if len(payload) < 1:
                return

            msg_type = MessageType(payload[0])
            inner = payload[1:] if len(payload) > 1 else b""

            handler = CONTROL_HANDLERS.get(msg_type)
            if handler:
                packets = handler(cs.session, inner)
                for p in packets:
                    self.transport.sendto(p, addr)

                if cs.session.is_established and cs.data is None:
                    cs.data = DataChannel(
                        cs.session.session_id,
                        cs.session.peer_session_id or b"",
                        cs.session.cipher,
                    )
                    logger.info("Server: data channel ready for %s", addr)

                    pool = self.config.ifconfig_pool
                    if pool and "-" in pool:
                        start_ip = pool.split("-")[0]
                        cs.virtual_ip = start_ip
                        self.ip_to_addr[start_ip] = addr
                        logger.info("Assigned IP %s to %s", start_ip, addr)

        elif opcode_val == Opcode.DATA:
            if cs.is_ready:
                plain = cs.data.decrypt(data)
                if plain:
                    self.tun.write(plain)


class ServerProtocol(asyncio.DatagramProtocol):
    def __init__(self, server: VpnServer):
        self.server = server
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        self.server.handle_udp_data(data, addr)

    def error_received(self, exc: Exception) -> None:
        logger.error("Socket error: %s", exc)


def _ipv4_dest(packet: bytes) -> str | None:
    if len(packet) < 20:
        return None
    version_ihl = packet[0]
    ihl = (version_ihl & 0x0f) * 4
    if len(packet) < ihl + 4:
        return None
    dest = packet[ihl + 4:ihl + 8]
    if len(dest) == 4:
        return ".".join(str(b) for b in dest)
    return None
