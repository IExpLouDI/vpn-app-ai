import asyncio
import logging
import time

from .config import Config
from .tun import TunInterface
from .protocol.messages import Opcode, MessageType
from .protocol.packet import decode_packet
from .protocol.control import (
    Session, client_start_handshake, client_handle_reset_ack,
    client_handle_server_hello, server_handle_client_finished,
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

    @property
    def client_ip(self) -> str:
        if self.config.ifconfig:
            return self.config.ifconfig
        return "10.8.0.2/24"

    async def run(self) -> None:
        if not self.config.remote:
            logger.error("No remote address specified")
            return

        logger.info("Connecting to %s:%d", self.config.remote, self.config.port)
        logger.info("TUN IP: %s", self.client_ip)

        if self.config.ca and self.config.cert and self.config.key:
            self.session.configure(self.config.ca, self.config.cert, self.config.key)

        self.tun = TunInterface(self.config.dev)
        self.tun.open()
        self.tun.set_ip(self.client_ip)
        self.tun.set_mtu(1500)

        loop = asyncio.get_event_loop()

        transport, protocol = await loop.create_datagram_endpoint(
            lambda: ClientProtocol(self),
            remote_addr=(self.config.remote, self.config.port),
        )
        self.transport = transport
        loop.add_reader(self.tun.fileno(), self._on_tun_readable)

        self._running = True

        packets = client_start_handshake(self.session)
        for p in packets:
            self.transport.sendto(p)
        logger.info("Sent HARD_RESET_CLIENT")

        try:
            while self._running:
                if not self._handshake_done and self.session.state.value >= 6:
                    self._handshake_done = True
                    self.data = DataChannel(
                        self.session.session_id,
                        self.session.peer_session_id or b"",
                        self.session.cipher,
                    )
                    logger.info("Data channel ready")

                if self._handshake_done:
                    await asyncio.sleep(3600)
                else:
                    await asyncio.sleep(0.1)

        except KeyboardInterrupt:
            self.stop()
        finally:
            loop.remove_reader(self.tun.fileno())
            self.tun.close()
            transport.close()

    def stop(self) -> None:
        self._running = False

    def _on_tun_readable(self) -> None:
        if not self._handshake_done or not self.data:
            return
        try:
            packet = self.tun.read()
        except OSError:
            return
        if not packet:
            return
        wire = self.data.encrypt(packet)
        self.transport.sendto(wire)

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
            elif msg_type == MessageType.CLIENT_FINISHED:
                packets = server_handle_client_finished(self.session, inner)
                for p in packets:
                    self.transport.sendto(p)

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
