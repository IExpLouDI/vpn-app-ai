import struct
import logging

from .messages import Opcode
from .packet import encode_packet, decode_packet
from ..crypto.cipher import Cipher

logger = logging.getLogger("pyvpn.protocol.data")

COMP_NONE = 0
COMP_LZO = 1

_HAS_LZ4 = False
_lz4_block = None
try:
    import lz4.block as _lz4_block
    _HAS_LZ4 = True
except ImportError:
    logger.warning("lz4 not available, compression disabled")


def derive_session_id(our_id: bytes, peer_id: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(our_id, peer_id))


class DataChannel:
    def __init__(self, our_id: bytes, peer_id: bytes, cipher: Cipher, comp_lzo: bool = False):
        self.shared_id = derive_session_id(our_id, peer_id)
        self.cipher = cipher
        self.packet_counter = 0
        self.comp_lzo = comp_lzo and _HAS_LZ4

    def encrypt(self, plaintext: bytes) -> bytes:
        self.packet_counter += 1
        counter_bytes = struct.pack("!I", self.packet_counter)
        aad = self.shared_id + counter_bytes

        if self.comp_lzo and len(plaintext) > 32:
            compressed = _lz4_block.compress(plaintext, mode="high_compression")
            if len(compressed) < len(plaintext):
                inner = struct.pack("!B", COMP_LZO) + compressed
            else:
                inner = struct.pack("!B", COMP_NONE) + plaintext
        else:
            inner = struct.pack("!B", COMP_NONE) + plaintext

        encrypted = self.cipher.encrypt(inner, aad)
        payload = counter_bytes + encrypted
        sid = int.from_bytes(self.shared_id, "big")
        return encode_packet(Opcode.DATA, sid, payload)

    def decrypt(self, wire_data: bytes) -> bytes | None:
        try:
            opcode, sid, payload = decode_packet(wire_data)
        except (ValueError, IndexError) as e:
            logger.warning("Failed to decode data packet: %s", e)
            return None

        if len(payload) < 4 + 12 + 16 + 1:
            logger.warning("Data packet too short")
            return None

        counter_bytes = payload[:4]
        encrypted = payload[4:]
        aad = self.shared_id + counter_bytes
        try:
            inner = self.cipher.decrypt(encrypted, aad)
        except Exception as e:
            logger.warning("Decryption failed: %s", e)
            return None

        if len(inner) < 1:
            return None

        comp_type = inner[0]
        raw = inner[1:]

        if comp_type == COMP_LZO:
            if not _HAS_LZ4 or not _lz4_block:
                logger.warning("LZO compressed data received but lz4 not available")
                return None
            try:
                return _lz4_block.decompress(raw)
            except Exception as e:
                logger.warning("Decompression failed: %s", e)
                return None
        elif comp_type == COMP_NONE:
            return raw
        else:
            logger.warning("Unknown compression type: %d", comp_type)
            return None
