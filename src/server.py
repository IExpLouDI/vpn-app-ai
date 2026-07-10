import asyncio
import ipaddress
import logging
import signal
import struct
import time

from .config import Config
from .protocol.control import (
    Session,
    server_handle_client_finished,
    server_handle_client_hello,
    server_handle_reset,
)
from .protocol.data import DataChannel
from .protocol.framing import frame_packet, read_frame
from .protocol.messages import MessageType, Opcode
from .protocol.packet import decode_packet
from .routing import IpPool, add_route, delete_route, enable_ip_forward
from .tun import TunInterface

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
        self.last_keepalive: float = 0.0
        self.writer: asyncio.StreamWriter | None = None

    @property
    def is_ready(self) -> bool:
        return self.session.is_established and self.data is not None

    @property
    def client_id(self) -> str:
        return str(self.addr)


class VpnServer:
    def __init__(self, config: Config):
        self.config = config
        self.tun: TunInterface | None = None
        self.transport: asyncio.DatagramTransport | None = None
        self.tcp_server: asyncio.AbstractServer | None = None
        self.clients: dict[tuple, ClientSession] = {}
        self.ip_to_addr: dict[str, tuple] = {}
        self._running = False

        self.ip_pool: IpPool | None = None
        if config.server:
            pool = config.ifconfig_pool or ""
            self.ip_pool = IpPool(config.server, pool)

    @property
    def server_ip(self) -> str:
        if self.config.server:
            net = ipaddress.IPv4Network(self.config.server, strict=False)
            return f"{net.network_address + 1}/{net.prefixlen}"
        if self.config.ifconfig:
            return self.config.ifconfig
        return "10.8.0.1/24"

    @property
    def _server_network(self) -> str:
        if self.config.server:
            return self.config.server
        return "10.8.0.0/24"

    @property
    def _is_tcp(self) -> bool:
        return self.config.proto == "tcp"

    async def run(self) -> None:
        logger.info("Server starting on port %d (%s)", self.config.port, self.config.proto)
        logger.info("TUN IP: %s", self.server_ip)

        self.tun = TunInterface(self.config.dev)
        self.tun.open()
        self.tun.set_ip(self.server_ip)
        self.tun.set_mtu(1500)

        if self.ip_pool:
            logger.info("IP pool: %s, server=%s, pool_size=%d",
                        self._server_network, self.server_ip.split("/")[0],
                        self.ip_pool.allocated_count() + len(self.ip_pool._available))

        enable_ip_forward()
        add_route(self._server_network, dev=self.config.dev)

        loop = asyncio.get_event_loop()

        if self._is_tcp:
            tcp_server = await asyncio.start_server(
                self._handle_tcp_client, "0.0.0.0", self.config.port,
            )
            self.tcp_server = tcp_server
            logger.info("TCP server listening on port %d", self.config.port)
        else:
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: ServerProtocol(self),
                local_addr=("0.0.0.0", self.config.port),
            )
            self.transport = transport

        loop.add_reader(self.tun.fileno(), self._on_tun_readable)

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.stop)
            except NotImplementedError:
                pass

        self._running = True
        logger.info("Server ready on port %d", self.config.port)

        try:
            while self._running:
                self._cleanup_stale()
                self._send_keepalives()
                for cs in self.clients.values():
                    if cs.data:
                        cs.data.cleanup_fragments()
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            self.stop()
        finally:
            self._cleanup()
            loop.remove_reader(self.tun.fileno())
            self.tun.close()
            if self.transport:
                self.transport.close()
            if self.tcp_server:
                self.tcp_server.close()
            logger.info("Server stopped")

    def stop(self) -> None:
        self._running = False

    def _cleanup(self) -> None:
        for cs in list(self.clients.values()):
            if cs.virtual_ip:
                delete_route(cs.virtual_ip, dev=self.config.dev)
            self._close_tcp_writer(cs)
        self.clients.clear()
        self.ip_to_addr.clear()
        delete_route(self._server_network, dev=self.config.dev)

    def _close_tcp_writer(self, cs: ClientSession) -> None:
        if cs.writer and not cs.writer.is_closing():
            cs.writer.close()

    def _send_to(self, cs: ClientSession, data: bytes) -> None:
        if self._is_tcp and cs.writer:
            cs.writer.write(frame_packet(data))
        elif self.transport:
            self.transport.sendto(data, cs.addr)

    def _send_keepalives(self) -> None:
        now = time.time()
        interval = self.config.keepalive_interval
        for addr, cs in list(self.clients.items()):
            if cs.is_ready and now - cs.last_keepalive >= interval:
                sid = int.from_bytes(cs.session.session_id, "big")
                payload = struct.pack("!B", MessageType.KEEPALIVE)
                packet = struct.pack("!B Q", Opcode.CONTROL, sid) + payload
                self._send_to(cs, packet)
                cs.last_keepalive = now

    def _cleanup_stale(self) -> None:
        now = time.time()
        timeout = self.config.keepalive_timeout
        to_remove = []
        for addr, cs in self.clients.items():
            if cs.session.is_established and now - cs.last_seen > timeout:
                logger.warning("Client %s stale (last seen %.1fs ago)", addr, now - cs.last_seen)
                to_remove.append(addr)
            elif not cs.session.is_established and cs.session.is_expired():
                to_remove.append(addr)
        for addr in to_remove:
            self._remove_client(addr)

    def _remove_client(self, addr: tuple) -> None:
        cs = self.clients.pop(addr, None)
        if cs:
            if cs.virtual_ip and cs.virtual_ip in self.ip_to_addr:
                del self.ip_to_addr[cs.virtual_ip]
                delete_route(cs.virtual_ip, dev=self.config.dev)
            if self.ip_pool and cs.virtual_ip:
                self.ip_pool.release(cs.client_id)
            self._close_tcp_writer(cs)
            logger.info("Client %s removed (IP: %s)", addr, cs.virtual_ip)

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

        for wire in cs.data.encrypt(packet):
            self._send_to(cs, wire)

    def _get_or_create_session(self, addr: tuple, writer: asyncio.StreamWriter | None = None) -> ClientSession:
        if addr in self.clients:
            return self.clients[addr]
        session = Session(is_server=True)
        if self.config.ca and self.config.cert and self.config.key:
            session.configure(self.config.ca, self.config.cert, self.config.key)
        cs = ClientSession(addr, session)
        cs.writer = writer
        self.clients[addr] = cs
        return cs

    def _assign_ip_to_client(self, cs: ClientSession) -> str | None:
        if not self.ip_pool:
            return None
        ip = self.ip_pool.allocate(cs.client_id)
        if ip:
            cs.virtual_ip = ip
            self.ip_to_addr[ip] = cs.addr
            logger.info("Mapped %s -> %s", ip, cs.addr)

            cs.session.assigned_ip = ip
            sid = int.from_bytes(cs.session.session_id, "big")
            ip_payload = struct.pack("!B", MessageType.IP_ASSIGN) + ip.encode("utf-8")
            packet = struct.pack("!B Q", Opcode.CONTROL, sid) + ip_payload
            self._send_to(cs, packet)

            add_route(ip, dev=self.config.dev)

        return ip

    async def _handle_tcp_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        addr = writer.get_extra_info("peername")
        logger.info("TCP client connected: %s", addr)

        self._get_or_create_session(addr, writer)

        try:
            while self._running:
                data = await read_frame(reader)
                if data is None:
                    break
                self.handle_udp_data(data, addr)
        except ConnectionError:
            pass
        finally:
            self._remove_client(addr)

    def handle_udp_data(self, data: bytes, addr: tuple) -> None:
        if len(data) < 1:
            return

        opcode_val = data[0]

        if opcode_val == Opcode.HARD_RESET_CLIENT:
            cs = self._get_or_create_session(addr)
            packets = server_handle_reset(cs.session, data)
            for p in packets:
                self._send_to(cs, p)
            return

        if opcode_val == Opcode.HARD_RESET_SERVER:
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

            if msg_type in CONTROL_HANDLERS:
                handler = CONTROL_HANDLERS[msg_type]
                packets = handler(cs.session, inner)
                for p in packets:
                    self._send_to(cs, p)

                if cs.session.is_established and cs.data is None:
                    cs.data = DataChannel(
                        cs.session.session_id,
                        cs.session.peer_session_id or b"",
                        cs.session.cipher,
                        comp_lzo=self.config.comp_lzo,
                    )
                    self._assign_ip_to_client(cs)
                    logger.info("Client %s ready (IP: %s)", addr, cs.virtual_ip)
            elif msg_type == MessageType.KEEPALIVE:
                pass

        elif opcode_val == Opcode.DATA:
            if cs.is_ready:
                plain = cs.data.decrypt(data)
                if plain:
                    self.tun.write(plain)


class ServerProtocol(asyncio.DatagramProtocol):
    def __init__(self, server: VpnServer):
        self.server = server

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.server.transport = transport

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
