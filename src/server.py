import asyncio
import logging

from .config import Config

logger = logging.getLogger("pyvpn.server")


class VpnServer:
    def __init__(self, config: Config):
        self.config = config
        self._running = False

    async def run(self) -> None:
        self._running = True
        logger.info("Server starting on port %d", self.config.port)

        loop = asyncio.get_event_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: ServerProtocol(self),
            local_addr=("0.0.0.0", self.config.port),
        )

        try:
            while self._running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            transport.close()
            logger.info("Server stopped")


class ServerProtocol(asyncio.DatagramProtocol):
    def __init__(self, server: VpnServer):
        self.server = server
        self.clients: dict[tuple, dict] = {}

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        if addr not in self.clients:
            self.clients[addr] = {"addr": addr}
            logger.info("New client: %s", addr)

        if self.server.config.verb >= 3:
            logger.debug("Received %d bytes from %s", len(data), addr)

    def error_received(self, exc: Exception) -> None:
        logger.error("Socket error: %s", exc)
