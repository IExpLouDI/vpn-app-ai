import sys
import asyncio
import logging

from config import Config
from cli import parse_args

logger = logging.getLogger("pyvpn")


def setup_logging(verb: int) -> None:
    level = {
        0: logging.WARNING,
        1: logging.INFO,
        2: logging.DEBUG,
    }.get(verb, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


async def run_server(cfg: Config) -> None:
    from server import VpnServer
    server = VpnServer(cfg)
    await server.run()


async def run_client(cfg: Config) -> None:
    from client import VpnClient
    client = VpnClient(cfg)
    await client.run()


def main(argv: list[str] | None = None) -> None:
    cfg = parse_args(argv)
    setup_logging(cfg.verb)

    if cfg.get_mode() == "server":
        asyncio.run(run_server(cfg))
    else:
        asyncio.run(run_client(cfg))


if __name__ == "__main__":
    main()
