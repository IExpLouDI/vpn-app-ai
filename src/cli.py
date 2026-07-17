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
        default=None,
        help="UDP port (default: 1194)",
    )
    parser.add_argument(
        "--proto",
        choices=["udp", "tcp"],
        default=None,
        help="Transport protocol (default: udp)",
    )
    parser.add_argument(
        "--dev",
        default=None,
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
        default=None,
        help="Data channel cipher (default: AES-256-GCM)",
    )
    parser.add_argument(
        "--comp-lzo",
        action="store_true",
        default=None,
        help="Enable LZ4 compression (directive name kept for OpenVPN compatibility)",
    )
    parser.add_argument(
        "--keepalive",
        nargs=2,
        type=int,
        metavar=("INTERVAL", "TIMEOUT"),
        default=None,
        help="Keepalive interval and timeout (default: 10 120)",
    )
    parser.add_argument(
        "--verb",
        type=int,
        default=None,
        choices=range(0, 5),
        help="Verbosity level (0-4)",
    )
    parser.add_argument(
        "--redirect-gateway",
        action="store_true",
        default=None,
        help="Redirect all traffic through VPN",
    )
    parser.add_argument(
        "--status",
        metavar="FILE",
        help="Write status file periodically (e.g., /tmp/vpn.status)",
    )
    parser.add_argument(
        "--user",
        metavar="USER",
        help="Drop root privileges to this user after setup (privilege separation)",
    )

    ns = parser.parse_args(argv)

    # Defaults come from the Config dataclass (or the config file); only
    # explicitly provided CLI flags override them.
    cfg = Config.from_file(ns.config) if ns.config else Config()

    for key, val in vars(ns).items():
        if val is None or key == "config":
            continue
        if key == "keepalive":
            cfg.keepalive_interval, cfg.keepalive_timeout = val
        elif key == "status":
            cfg.status_file = val
        elif hasattr(cfg, key):
            setattr(cfg, key, val)
    return cfg
