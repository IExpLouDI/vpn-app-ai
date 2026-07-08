import enum
import os
import struct
import logging
import time

from cryptography.x509 import Certificate, load_pem_x509_certificate
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa, padding
from cryptography.hazmat.backends import default_backend

from ..crypto.certificates import load_certificate, load_private_key, verify_certificate
from ..crypto.key_exchange import (
    generate_ephemeral_keypair, public_key_from_bytes,
    public_key_to_bytes, derive_shared_key,
)
from ..crypto.cipher import Cipher
from .messages import Opcode, MessageType, HANDSHAKE_TIMEOUT
from .packet import encode_packet, encode_handshake_message, decode_packet

logger = logging.getLogger("pyvpn.protocol.control")


class HandshakeState(enum.Enum):
    IDLE = 0
    RESET_SENT = 1
    RESET_RCVD = 2
    HELLO_SENT = 3
    ESTABLISHED = 6
    ERROR = 7


class Session:
    def __init__(self, is_server: bool = False):
        self.session_id = os.urandom(8)
        self.peer_session_id: bytes | None = None
        self.state = HandshakeState.IDLE
        self.is_server = is_server
        self.cipher: Cipher | None = None
        self.peer_cert: Certificate | None = None

        self._private_eph, self._public_eph = generate_ephemeral_keypair()
        self._peer_pub_eph: bytes | None = None
        self._local_cert_path: str | None = None
        self._local_key_path: str | None = None
        self._ca_path: str | None = None
        self._local_cert_bytes: bytes | None = None

        self.last_rx: float = time.time()
        self.last_tx: float = 0.0
        self.created_at: float = time.time()
        self.assigned_ip: str | None = None

    def configure(self, ca_path: str, cert_path: str, key_path: str) -> None:
        self._ca_path = ca_path
        self._local_cert_path = cert_path
        self._local_key_path = key_path
        if cert_path:
            with open(cert_path, "rb") as f:
                self._local_cert_bytes = f.read()

    @property
    def is_established(self) -> bool:
        return self.state == HandshakeState.ESTABLISHED

    def is_expired(self, timeout: float = HANDSHAKE_TIMEOUT) -> bool:
        return self.state not in (HandshakeState.ESTABLISHED, HandshakeState.IDLE) and \
            (time.time() - self.created_at) > timeout


def _sign(key_path: str | None, data: bytes) -> bytes:
    if not key_path:
        return b""
    key = load_private_key(key_path)
    if isinstance(key, ec.EllipticCurvePrivateKey):
        return key.sign(data, ec.ECDSA(hashes.SHA256()))
    elif isinstance(key, rsa.RSAPrivateKey):
        return key.sign(data, padding.PKCS1v15(), hashes.SHA256())
    return b""


def _verify(cert: Certificate, data: bytes, sig: bytes) -> bool:
    try:
        pk = cert.public_key()
        if isinstance(pk, ec.EllipticCurvePublicKey):
            pk.verify(sig, data, ec.ECDSA(hashes.SHA256()))
        elif isinstance(pk, rsa.RSAPublicKey):
            pk.verify(sig, data, padding.PKCS1v15(), hashes.SHA256())
        else:
            return False
        return True
    except Exception:
        return False


def _verify_peer_cert(session: Session) -> bool:
    if not session._ca_path or not session.peer_cert:
        return True
    ca = load_certificate(session._ca_path)
    return verify_certificate(session.peer_cert, ca)


def _pack_cert_and_pubkey(cert_bytes: bytes, pub_bytes: bytes) -> bytes:
    return struct.pack("!H", len(cert_bytes)) + cert_bytes + \
           struct.pack("!H", len(pub_bytes)) + pub_bytes


def _unpack_hello(payload: bytes, offset: int = 0) -> tuple[bytes, bytes, int]:
    cert_len = struct.unpack("!H", payload[offset:offset+2])[0]
    offset += 2
    cert_data = payload[offset:offset+cert_len]
    offset += cert_len
    pub_len = struct.unpack("!H", payload[offset:offset+2])[0]
    offset += 2
    pub_data = payload[offset:offset+pub_len]
    offset += pub_len
    return cert_data, pub_data, offset


def client_start_handshake(session: Session) -> list[bytes]:
    session.state = HandshakeState.RESET_SENT
    sid = int.from_bytes(session.session_id, "big")
    return [encode_packet(Opcode.HARD_RESET_CLIENT, sid)]


def server_handle_reset(session: Session, raw: bytes) -> list[bytes]:
    opcode, sid, _ = decode_packet(raw)
    if opcode != Opcode.HARD_RESET_CLIENT:
        return []
    session.peer_session_id = struct.pack("!Q", sid)
    session.state = HandshakeState.RESET_RCVD
    session.last_rx = time.time()
    sid = int.from_bytes(session.session_id, "big")
    return [encode_packet(Opcode.HARD_RESET_SERVER, sid)]


def client_handle_reset_ack(session: Session, raw: bytes) -> list[bytes]:
    opcode, sid, _ = decode_packet(raw)
    if opcode != Opcode.HARD_RESET_SERVER:
        return []
    session.peer_session_id = struct.pack("!Q", sid)
    session.state = HandshakeState.RESET_RCVD

    if not session._local_cert_bytes:
        logger.error("Client: no local cert configured")
        session.state = HandshakeState.ERROR
        return []

    my_pub = public_key_to_bytes(session._public_eph)
    inner = _pack_cert_and_pubkey(session._local_cert_bytes, my_pub)
    sid = int.from_bytes(session.session_id, "big")
    packet = encode_handshake_message(MessageType.CLIENT_HELLO, sid, inner)
    logger.info("Client: sent CLIENT_HELLO")
    return [packet]


def _handshake_salt(session: Session) -> bytes:
    a = session.session_id
    b = session.peer_session_id or b""
    return a + b if a < b else b + a


def server_handle_client_hello(session: Session, payload: bytes) -> list[bytes]:
    try:
        cert_data, pub_data, _ = _unpack_hello(payload)
        session._peer_pub_eph = pub_data
        session.peer_cert = load_pem_x509_certificate(cert_data, default_backend())

        if not _verify_peer_cert(session):
            logger.error("Server: CLIENT_HELLO cert verification FAILED")
            session.state = HandshakeState.ERROR
            return []

        peer_pub = public_key_from_bytes(pub_data)
        salt = _handshake_salt(session)
        shared = derive_shared_key(session._private_eph, peer_pub, salt=salt)
        session.cipher = Cipher(shared)
        logger.info("Server: session key derived")

        my_pub = public_key_to_bytes(session._public_eph)
        sig_data = pub_data + my_pub
        sig = _sign(session._local_key_path, sig_data)

        cert_bytes = b""
        if session._local_cert_bytes:
            cert_bytes = session._local_cert_bytes
        inner = _pack_cert_and_pubkey(cert_bytes, my_pub) + \
                struct.pack("!H", len(sig)) + sig

        sid = int.from_bytes(session.session_id, "big")
        packet = encode_handshake_message(MessageType.SERVER_HELLO, sid, inner)
        session.state = HandshakeState.HELLO_SENT
        logger.info("Server: sent SERVER_HELLO")
        return [packet]

    except Exception as e:
        logger.error("CLIENT_HELLO error: %s", e)
        session.state = HandshakeState.ERROR
        return []


def client_handle_server_hello(session: Session, payload: bytes) -> list[bytes]:
    try:
        cert_data, pub_data, offset = _unpack_hello(payload)
        session._peer_pub_eph = pub_data

        sig_len = struct.unpack("!H", payload[offset:offset+2])[0]
        offset += 2
        sig = payload[offset:offset+sig_len]

        session.peer_cert = load_pem_x509_certificate(cert_data, default_backend())

        if not _verify_peer_cert(session):
            logger.error("Client: SERVER_HELLO cert verification FAILED")
            session.state = HandshakeState.ERROR
            return []

        peer_pub = public_key_from_bytes(pub_data)
        salt = _handshake_salt(session)
        shared = derive_shared_key(session._private_eph, peer_pub, salt=salt)
        session.cipher = Cipher(shared)
        logger.info("Client: session key derived")

        my_pub = public_key_to_bytes(session._public_eph)
        check_data = my_pub + pub_data
        if not _verify(session.peer_cert, check_data, sig):
            logger.error("Client: SERVER_HELLO signature FAILED")
            session.state = HandshakeState.ERROR
            return []

        session.state = HandshakeState.ESTABLISHED
        logger.info("Client: handshake ESTABLISHED")

        finish_sig = _sign(session._local_key_path, my_pub + pub_data)
        inner = struct.pack("!H", len(finish_sig)) + finish_sig
        sid = int.from_bytes(session.session_id, "big")
        packet = encode_handshake_message(MessageType.CLIENT_FINISHED, sid, inner)
        return [packet]

    except Exception as e:
        logger.error("SERVER_HELLO error: %s", e)
        session.state = HandshakeState.ERROR
        return []


def server_handle_client_finished(session: Session, payload: bytes) -> list[bytes]:
    try:
        sig_len = struct.unpack("!H", payload[:2])[0]
        sig = payload[2:2+sig_len]

        my_pub = public_key_to_bytes(session._public_eph)
        check_data = (session._peer_pub_eph or b"") + my_pub
        if not _verify(session.peer_cert, check_data, sig):
            logger.error("Server: CLIENT_FINISHED signature FAILED")
            session.state = HandshakeState.ERROR
            return []

        session.state = HandshakeState.ESTABLISHED
        logger.info("Server: handshake ESTABLISHED")
        return []

    except Exception as e:
        logger.error("CLIENT_FINISHED error: %s", e)
        session.state = HandshakeState.ERROR
        return []
