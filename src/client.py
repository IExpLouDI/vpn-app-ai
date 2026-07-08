import asyncio
import logging
import signal
import struct
import subprocess

from .config import Config
from .tun import TunInterface
from .protocol.messages import Opcode, MessageType
from .protocol.packet import decode_packet
from .protocol.control import (
    Session, client_start_handshake, client_handle_reset_ack,
    client_handle_server_hello,
)
from .protocol.data import DataChannel

logger = logging.getLogger("pyvpn.client")


class VpnClient:
    def __init__(self, config: Config):
        self.config = config
        self.tun: TunInterface | None = None
        self.transport: asyncio.DatagramTransport | None = None
        self.session = Session(is_server=False)
        self.data: DataChannel | None = None
        self._running = False
        self._handshake_done = False
        self._assigned_ip: str | None = None
        self._routes_added: list[list[str]] = []

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

        logger.info("Connecting to %s:%d", self.config.remote, self.config.port)

        if self.config.ca and self.config.cert and self.config.key:
            self.session.configure(self.config.ca, self.config.cert, self.config.key)

        self.tun = TunInterface(self.config.dev)
        self.tun.open()
        self.tun.set_mtu(1500)

        loop = asyncio.get_event_loop()

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

        self._running = True

        packets = client_start_handshake(self.session)
        for p in packets:
            self.transport.sendto(p)
        logger.info("Sent HARD_RESET_CLIENT")

        try:
            while self._running:
                if not self._handshake_done and self.session.is_established:
                    self._handshake_done = True
                    self.data = DataChannel(
                        self.session.session_id,
                        self.session.peer_session_id or b"",
                        self.session.cipher,
                    )
                    logger.info("Data channel ready (waiting for IP assignment)")

                if self._handshake_done and self._assigned_ip:
                    await asyncio.sleep(3600)
                else:
                    await asyncio.sleep(0.1)

        except KeyboardInterrupt:
            self.stop()
        finally:
            self._cleanup()
            loop.remove_reader(self.tun.fileno())
            self.tun.close()
            if transport:
                transport.close()

    def stop(self) -> None:
        self._running = False

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
        self.transport.sendto(wire)

    def _handle_ip_assign(self, ip_str: str) -> None:
        logger.info("Received IP assignment: %s", ip_str)
        self._assigned_ip = ip_str

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

        opcode_val = data[0]

        if opcode_val == Opcode.HARD_RESET_SERVER:
            packets = client_handle_reset_ack(self.session, data)
            for p in packets:
                self.transport.sendto(p)
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
                    self.transport.sendto(p)
            elif msg_type == MessageType.IP_ASSIGN:
                ip_str = inner.decode("utf-8")
                self._handle_ip_assign(ip_str)
            elif msg_type == MessageType.KEEPALIVE:
                pass

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
