import logging
import socket
import ssl
import struct
import threading

from cryptography.hazmat.backends import default_backend
from cryptography.x509 import NameOID, load_der_x509_certificate

from crypto.cipher import Cipher

logger = logging.getLogger("pyvpn.protocol.tls_channel")

TLS_VERSION = ssl.TLSVersion.TLSv1_3

_HEADER = struct.Struct("!I")


class TLSChannelError(Exception):
    pass


def _make_server_context(ca_path: str, cert_path: str, key_path: str) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = TLS_VERSION
    ctx.maximum_version = TLS_VERSION
    ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
    ctx.load_verify_locations(cafile=ca_path)
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def _make_client_context(
    ca_path: str,
    cert_path: str,
    key_path: str,
    server_hostname: str | None = None,
) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = TLS_VERSION
    ctx.maximum_version = TLS_VERSION
    ctx.load_verify_locations(cafile=ca_path)
    ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
    ctx.check_hostname = False
    return ctx


class TLSControlChannel:
    def __init__(self, sock: ssl.SSLSocket):
        self._sock = sock
        self._lock = threading.Lock()
        der = sock.getpeercert(binary_form=True)
        self.peer_cert_der: bytes | None = der
        self.peer_common_name: str | None = _common_name_from_der(der) if der else None
        logger.info("TLS control channel established (peer: %s)", self.peer_common_name)

    @property
    def version(self) -> str:
        return self._sock.version()

    def send(self, data: bytes) -> None:
        frame = _HEADER.pack(len(data)) + data
        with self._lock:
            self._sock.sendall(frame)

    def recv(self) -> bytes:
        header = self._recv_exact(_HEADER.size)
        (length,) = _HEADER.unpack(header)
        return self._recv_exact(length)

    def _recv_exact(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            try:
                chunk = self._sock.recv(n - len(buf))
            except OSError as e:
                raise TLSChannelError(f"TLS control channel recv failed: {e}") from e
            if not chunk:
                raise TLSChannelError("TLS control channel closed by peer")
            buf.extend(chunk)
        return bytes(buf)

    def exchange_data_key(self, initiator: bool) -> bytes:
        if initiator:
            key = Cipher.generate_key()
            self.send(key)
            return key
        key = self.recv()
        self.send(key)
        return key

    def close(self) -> None:
        try:
            self._sock.unwrap()
        except Exception:
            pass
        try:
            self._sock.close()
        except Exception:
            pass


def _common_name_from_der(der: bytes) -> str | None:
    try:
        cert = load_der_x509_certificate(der, default_backend())
        return cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    except Exception:
        return None


class TLSControlServer:
    def __init__(self, host: str, port: int, ca_path: str, cert_path: str, key_path: str):
        self._ctx = _make_server_context(ca_path, cert_path, key_path)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((host, port))
        self._sock.listen(8)
        logger.info("TLS control server listening on %s:%d", host, port)

    @property
    def address(self) -> tuple[str, int]:
        return self._sock.getsockname()

    def accept(self) -> TLSControlChannel:
        conn, _ = self._sock.accept()
        ssl_sock = self._ctx.wrap_socket(conn, server_side=True)
        return TLSControlChannel(ssl_sock)

    def close(self) -> None:
        try:
            self._sock.close()
        except Exception:
            pass


def connect_client(
    host: str,
    port: int,
    ca_path: str,
    cert_path: str,
    key_path: str,
    server_hostname: str | None = None,
    timeout: float = 10.0,
) -> TLSControlChannel:
    ctx = _make_client_context(ca_path, cert_path, key_path, server_hostname)
    raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw.settimeout(timeout)
    raw.connect((host, port))
    ssl_sock = ctx.wrap_socket(raw, server_side=False, server_hostname=server_hostname)
    return TLSControlChannel(ssl_sock)
