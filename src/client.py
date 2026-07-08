import asyncio
import logging

from config import Config

logger = logging.getLogger("pyvpn.client")


class VpnClient:
    def __init__(self, config: Config):
        self.config = config
        self._running = False

    async def run(self) -> None:
        if not self.config.remote:
            logger.error("No remote address specified")
            return

        self._running = True
        logger.info("Connecting to %s:%d", self.config.remote, self.config.port)

        loop = asyncio.get_event_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: ClientProtocol(self),
            remote_addr=(self.config.remote, self.config.port),
        )

        try:
            while self._running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            transport.close()
            logger.info("Client stopped")


class ClientProtocol(asyncio.DatagramProtocol):
    def __init__(self, client: VpnClient):
        self.client = client

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport
        logger.info("Connected to server")

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        if self.client.config.verb >= 3:
            logger.debug("Received %d bytes from %s", len(data), addr)

    def error_received(self, exc: Exception) -> None:
        logger.error("Socket error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        logger.info("Connection lost: %s", exc)
