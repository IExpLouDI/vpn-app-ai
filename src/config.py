from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    dev: str = "tun"
    proto: str = "udp"
    port: int = 1194
    remote: Optional[str] = None
    ifconfig: Optional[str] = None
    server: Optional[str] = None
    ifconfig_pool: Optional[str] = None
    ca: Optional[str] = None
    cert: Optional[str] = None
    key: Optional[str] = None
    cipher: str = "AES-256-GCM"
    comp_lzo: bool = False
    keepalive_interval: int = 10
    keepalive_timeout: int = 120
    verb: int = 1
    redirect_gateway: bool = False
    extra_options: dict = field(default_factory=dict)

    def get_mode(self) -> str:
        return "server" if self.server else "client"

    @classmethod
    def from_file(cls, path: str) -> "Config":
        return _parse_config(path)

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


DIRECTIVES = {
    "dev": "dev",
    "proto": "proto",
    "port": "port",
    "remote": "remote",
    "ifconfig": "ifconfig",
    "server": "server",
    "ifconfig-pool": "ifconfig_pool",
    "ca": "ca",
    "cert": "cert",
    "key": "key",
    "cipher": "cipher",
    "comp-lzo": "comp_lzo",
    "keepalive": ("keepalive_interval", "keepalive_timeout"),
    "verb": "verb",
    "redirect-gateway": "redirect_gateway",
}


def _parse_config(path: str) -> Config:
    kwargs = {}

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue

            parts = line.split()
            directive = parts[0]
            args = parts[1:]

            attr = DIRECTIVES.get(directive)
            if attr is None:
                kwargs.setdefault("extra_options", {})[directive] = args
                continue

            if isinstance(attr, tuple):
                for a, v in zip(attr, args):
                    _set_value(kwargs, a, v)
            elif directive in ("comp-lzo", "redirect-gateway"):
                kwargs[attr] = True
            else:
                _set_value(kwargs, attr, args[0] if len(args) == 1 else args)

    return Config(**kwargs)


def _set_value(kwargs: dict, key: str, value: str) -> None:
    field_type = Config.__dataclass_fields__[key].type
    if field_type == int:
        kwargs[key] = int(value)
    elif field_type == bool:
        kwargs[key] = value.lower() in ("yes", "true", "1")
    else:
        kwargs[key] = value
