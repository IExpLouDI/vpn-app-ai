import asyncio
import logging
import signal
import struct
import subprocess
import time

from .config import Config
from .tun import TunInterface
from .protocol.messages import Opcode, MessageType
from .protocol.packet import decode_packet, encode_packet
from .protocol.control import (
    Session, client_start_handshake, client_handle_reset_ack,
    client_handle_server_hello,
)
from .protocol.data import DataChannel
from .protocol.framing import frame_packet, read_frame

logger = logging.getLogger("pyvpn.client")


class VpnClient:
    def __init__(self, config: Config):
        self.config = config
        self.tun: TunInterface | None = None
        self.transport: asyncio.DatagramTransport | None = None
        self.tcp_reader: asyncio.StreamReader | None = None
        self.tcp_writer: asyncio.StreamWriter | None = None
        self.session = Session(is_server=False)
        self.data: DataChannel | None = None
        self._running = False
        self._handshake_done = False
        self._assigned_ip: str | None = None
        self._routes_added: list[list[str]] = []
        self._last_seen: float = time.time()
        self._connected: bool = False

    @property
    def _is_tcp(self) -> bool:
        return self.config.proto == "tcp"

    @property
    def client_ip(self) -> str:
        if self._assigned_ip:
            return self._assigned_ip
        if self.config.ifconfig:
            return self.config.ifconfig
        return "10.8.0.2/24"

    async def run(self) -> None:
        if not self.config.remote:
            logger.error("No remote address specified")
            return

        while self._running or not self._connected:
            self._running = True
            self._handshake_done = False
            self._assigned_ip = None
            self.data = None
            self.session = Session(is_server=False)
            if self.config.ca and self.config.cert and self.config.key:
                self.session.configure(self.config.ca, self.config.cert, self.config.key)

            if self.tun is None:
                self.tun = TunInterface(self.config.dev)
                self.tun.open()
                self.tun.set_mtu(1500)

            await self._connect()

            if not self._running:
                break
            if self._connected:
                return

            logger.info("Retrying in 5 seconds...")
            await asyncio.sleep(5)

    async def _connect(self) -> None:
        logger.info("Connecting to %s:%d (%s)",
                     self.config.remote, self.config.port, self.config.proto)

        loop = asyncio.get_event_loop()
        tcp_read_task = None

        if self._is_tcp:
            try:
                self.tcp_reader, self.tcp_writer = await asyncio.open_connection(
                    self.config.remote, self.config.port,
                )
            except (OSError, ConnectionError) as e:
                logger.error("TCP connection failed: %s", e)
                self._connected = False
                return
            logger.info("TCP connection established")
            tcp_read_task = asyncio.create_task(self._tcp_read_loop())
        else:
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: ClientProtocol(self),
                remote_addr=(self.config.remote, self.config.port),
            )
            self.transport = transport

        loop.add_reader(self.tun.fileno(), self._on_tun_readable)

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.stop)
            except NotImplementedError:
                pass

        packets = client_start_handshake(self.session)
        for p in packets:
            self._send(p)
        logger.info("Sent HARD_RESET_CLIENT")

        try:
            while self._running:
                if not self._handshake_done and self.session.is_established:
                    self._handshake_done = True
                    self.data = DataChannel(
                        self.session.session_id,
                        self.session.peer_session_id or b"",
                        self.session.cipher,
                        comp_lzo=self.config.comp_lzo,
                    )
                    logger.info("Data channel ready (waiting for IP assignment)")

                now = time.time()
                if self._handshake_done and self._assigned_ip:
                    if now - self._last_seen > self.config.keepalive_timeout:
                        logger.warning("Connection timed out, reconnecting...")
                        self._connected = False
                        break
                elif self._handshake_done and now - self._last_seen > self.config.keepalive_timeout:
                    logger.warning("Handshake timeout, reconnecting...")
                    self._connected = False
                    break

                await asyncio.sleep(1)

        except KeyboardInterrupt:
            self.stop()
        finally:
            self._cleanup()
            loop.remove_reader(self.tun.fileno())
            if self.transport:
                self.transport.close()
            if self.tcp_writer:
                self.tcp_writer.close()
            if tcp_read_task:
                tcp_read_task.cancel()

    def _send(self, data: bytes) -> None:
        if self._is_tcp and self.tcp_writer:
            self.tcp_writer.write(frame_packet(data))
        elif self.transport:
            self.transport.sendto(data)

    async def _tcp_read_loop(self) -> None:
        try:
            while self._running and self.tcp_reader:
                data = await read_frame(self.tcp_reader)
                if data is None:
                    break
                self.handle_udp_data(data)
        except ConnectionError:
            pass
        except asyncio.CancelledError:
            pass

    def stop(self) -> None:
        self._running = False
        self._connected = False

    def _cleanup(self) -> None:
        for cmd in reversed(self._routes_added):
            del_cmd = ["ip", "route", "delete"] + cmd[2:]
            subprocess.run(del_cmd, capture_output=True)
        self._routes_added.clear()

    def _on_tun_readable(self) -> None:
        if not self._handshake_done or not self.data or not self._assigned_ip:
            return
        try:
            packet = self.tun.read()
        except OSError:
            return
        if not packet:
            return
        wire = self.data.encrypt(packet)
        self._send(wire)

    def _handle_ip_assign(self, ip_str: str) -> None:
        logger.info("Received IP assignment: %s", ip_str)
        self._assigned_ip = ip_str
        self._connected = True

        cidr = f"{ip_str}/24"
        self.tun.set_ip(cidr)

        server_ip = "10.8.0.1"
        route_cmd = ["ip", "route", "add", "10.8.0.0/24", "dev", self.config.dev]
        subprocess.run(route_cmd, capture_output=True)
        self._routes_added.append(route_cmd)

        if self.config.redirect_gateway:
            gw_cmd = [
                "ip", "route", "add", "default", "via", server_ip,
                "dev", self.config.dev, "metric", "50",
            ]
            subprocess.run(gw_cmd, capture_output=True)
            self._routes_added.append(gw_cmd)
            logger.info("Default route redirected via VPN")

        logger.info("TUN configured: %s/24 via %s", ip_str, self.config.dev)

    def handle_udp_data(self, data: bytes) -> None:
        if len(data) < 1:
            return
        self._last_seen = time.time()

        opcode_val = data[0]

        if opcode_val == Opcode.HARD_RESET_SERVER:
            packets = client_handle_reset_ack(self.session, data)
            for p in packets:
                self._send(p)
            return

        if opcode_val == Opcode.CONTROL:
            try:
                _, _, payload = decode_packet(data)
            except (ValueError, IndexError):
                return
            if len(payload) < 1:
                return

            msg_type = MessageType(payload[0])
            inner = payload[1:] if len(payload) > 1 else b""

            if msg_type == MessageType.SERVER_HELLO:
                packets = client_handle_server_hello(self.session, inner)
                for p in packets:
                    self._send(p)
            elif msg_type == MessageType.IP_ASSIGN:
                ip_str = inner.decode("utf-8")
                self._handle_ip_assign(ip_str)
            elif msg_type == MessageType.KEEPALIVE:
                sid = int.from_bytes(self.session.session_id, "big")
                resp = encode_packet(Opcode.CONTROL, sid, struct.pack("!B", MessageType.KEEPALIVE))
                self._send(resp)

            return

        if opcode_val == Opcode.DATA and self.data:
            plain = self.data.decrypt(data)
            if plain:
                self.tun.write(plain)


class ClientProtocol(asyncio.DatagramProtocol):
    def __init__(self, client: VpnClient):
        self.client = client
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport
        logger.info("UDP connection established")

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        self.client.handle_udp_data(data)

    def error_received(self, exc: Exception) -> None:
        logger.error("Socket error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        logger.info("Connection lost: %s", exc)
