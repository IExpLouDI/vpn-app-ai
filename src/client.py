import asyncio
import logging

from .config import Config
from .tun import TunInterface

logger = logging.getLogger("pyvpn.client")


class VpnClient:
    def __init__(self, config: Config):
        self.config = config
        self.tun: TunInterface | None = None
        self.transport: asyncio.DatagramTransport | None = None
        self._running = False

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

        self.tun = TunInterface(self.config.dev)
        self.tun.open()
        self.tun.set_ip(self.client_ip)
        self.tun.set_mtu(1500)
        logger.info("TUN interface %s is up", self.config.dev)

        loop = asyncio.get_event_loop()

        transport, protocol = await loop.create_datagram_endpoint(
            lambda: ClientProtocol(self),
            remote_addr=(self.config.remote, self.config.port),
        )
        self.transport = transport

        loop.add_reader(self.tun.fileno(), self._on_tun_readable)

        self._running = True
        logger.info("Client is connected")

        try:
            while self._running:
                await asyncio.sleep(3600)
        except KeyboardInterrupt:
            self.stop()
        finally:
            loop.remove_reader(self.tun.fileno())
            self.tun.close()
            transport.close()
            logger.info("Client stopped")

    def stop(self) -> None:
        self._running = False

    def _on_tun_readable(self) -> None:
        try:
            packet = self.tun.read()
        except OSError:
            return

        if not packet:
            return

        self.transport.sendto(packet)


class ClientProtocol(asyncio.DatagramProtocol):
    def __init__(self, client: VpnClient):
        self.client = client
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport
        logger.info("UDP connection established")

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        try:
            self.client.tun.write(data)
        except OSError as e:
            logger.error("TUN write error: %s", e)

    def error_received(self, exc: Exception) -> None:
        logger.error("Socket error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        logger.info("Connection lost: %s", exc)
