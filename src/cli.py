import argparse

from config import Config


def parse_args(argv: list[str] | None = None) -> Config:
    parser = argparse.ArgumentParser(prog="pyvpn", description="Python VPN")

    parser.add_argument(
        "--config", "-c",
        help="Path to configuration file",
    )
    parser.add_argument(
        "--remote",
        help="Server address (client mode)",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=1194,
        help="UDP port (default: 1194)",
    )
    parser.add_argument(
        "--proto",
        choices=["udp", "tcp"],
        default="udp",
        help="Transport protocol (default: udp)",
    )
    parser.add_argument(
        "--dev",
        default="tun",
        help="TUN device name (default: tun)",
    )
    parser.add_argument(
        "--server",
        help="Server subnet in CIDR (server mode), e.g. 10.8.0.0/24",
    )
    parser.add_argument(
        "--ifconfig",
        help="Client IP/CIDR, e.g. 10.8.0.2/24",
    )
    parser.add_argument(
        "--ifconfig-pool",
        help="IP pool range for server allocation, e.g. 10.8.0.2-10.8.0.100",
    )
    parser.add_argument(
        "--ca",
        help="CA certificate file",
    )
    parser.add_argument(
        "--cert",
        help="Certificate file",
    )
    parser.add_argument(
        "--key",
        help="Private key file",
    )
    parser.add_argument(
        "--cipher",
        default="AES-256-GCM",
        help="Data channel cipher (default: AES-256-GCM)",
    )
    parser.add_argument(
        "--comp-lzo",
        action="store_true",
        help="Enable LZO compression",
    )
    parser.add_argument(
        "--keepalive",
        nargs=2,
        type=int,
        metavar=("INTERVAL", "TIMEOUT"),
        default=[10, 120],
        help="Keepalive interval and timeout",
    )
    parser.add_argument(
        "--verb",
        type=int,
        default=1,
        choices=range(0, 5),
        help="Verbosity level (0-4)",
    )
    parser.add_argument(
        "--redirect-gateway",
        action="store_true",
        help="Redirect all traffic through VPN",
    )
    parser.add_argument(
        "--status",
        metavar="FILE",
        help="Write status file periodically (e.g., /tmp/vpn.status)",
    )

    ns = parser.parse_args(argv)

    if ns.config:
        cfg = Config.from_file(ns.config)
        cli_overrides = {k: v for k, v in vars(ns).items()
                         if v is not None and k != "config"}
        for key, val in cli_overrides.items():
            attr = key.replace("-", "_")
            if hasattr(cfg, attr):
                setattr(cfg, attr, val)
        return cfg

    return Config(
        dev=ns.dev,
        proto=ns.proto,
        port=ns.port,
        remote=ns.remote,
        server=ns.server,
        ifconfig=ns.ifconfig,
        ifconfig_pool=ns.ifconfig_pool,
        ca=ns.ca,
        cert=ns.cert,
        key=ns.key,
        cipher=ns.cipher,
        comp_lzo=ns.comp_lzo,
        keepalive_interval=ns.keepalive[0],
        keepalive_timeout=ns.keepalive[1],
        verb=ns.verb,
        redirect_gateway=ns.redirect_gateway,
        status_file=ns.status,
    )
