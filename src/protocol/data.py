import logging
import struct
import time

from crypto.cipher import Cipher

from .messages import Opcode
from .packet import decode_packet, encode_packet
from .replay import ReplayWindow

logger = logging.getLogger("pyvpn.protocol.data")

COMP_NONE = 0
COMP_LZO = 1
FRAG_MASK = 0x80

MAX_PAYLOAD = 1400
FRAG_TIMEOUT = 5.0

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
    def __init__(self, our_id: bytes, peer_id: bytes, cipher: Cipher, comp_lzo: bool = False,
                 replay_window: int = 64):
        self.shared_id = derive_session_id(our_id, peer_id)
        self.cipher = cipher
        self.packet_counter = 0
        self.comp_lzo = comp_lzo and _HAS_LZ4
        self._fragments: dict[int, dict] = {}
        self.replay = ReplayWindow(replay_window)

    def _encrypt_one(self, plaintext: bytes, counter: int) -> bytes:
        counter_bytes = struct.pack("!I", counter)
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

    def encrypt(self, plaintext: bytes) -> list[bytes]:
        self.packet_counter += 1
        if len(plaintext) <= MAX_PAYLOAD:
            return [self._encrypt_one(plaintext, self.packet_counter)]

        start = self.packet_counter
        total = (len(plaintext) + MAX_PAYLOAD - 1) // MAX_PAYLOAD
        result = []

        for i in range(total):
            offset = i * MAX_PAYLOAD
            chunk = plaintext[offset:offset + MAX_PAYLOAD]
            frag_header = struct.pack("!BB", total, i)
            frag_payload = bytes([FRAG_MASK | COMP_NONE]) + frag_header + chunk
            encrypted = self._encrypt_one(frag_payload, start + i)
            result.append(encrypted)

        self.packet_counter = start + total - 1
        return result

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
        pkt_counter = struct.unpack("!I", counter_bytes)[0]

        if not self.replay.check(pkt_counter):
            logger.warning("Replay detected, dropping packet id=%d", pkt_counter)
            return None

        encrypted = payload[4:]
        aad = self.shared_id + counter_bytes
        try:
            inner = self.cipher.decrypt(encrypted, aad)
        except Exception as e:
            logger.warning("Decryption failed: %s", e)
            return None

        if len(inner) < 1:
            return None

        plain = self._decompress(inner)
        if plain is None:
            return None
        if len(plain) < 1:
            return plain

        if plain[0] & FRAG_MASK:
            if len(plain) < 4:
                return None
            total = plain[1]
            index = plain[2]
            raw = plain[3:]
            group_id = pkt_counter - index

            if group_id not in self._fragments:
                self._fragments[group_id] = {
                    "total": total,
                    "fragments": {},
                    "ts": time.time(),
                }

            buf = self._fragments[group_id]
            if buf["total"] != total:
                logger.warning("Fragment total mismatch, discarding")
                self._fragments.pop(group_id, None)
                return None

            buf["fragments"][index] = raw

            if len(buf["fragments"]) == total:
                data = b"".join(buf["fragments"][i] for i in range(total))
                self._fragments.pop(group_id, None)
                return data
            return None

        return plain

    def _decompress(self, inner: bytes) -> bytes | None:
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

    def cleanup_fragments(self) -> None:
        now = time.time()
        stale = [gid for gid, buf in self._fragments.items()
                 if now - buf["ts"] > FRAG_TIMEOUT]
        for gid in stale:
            self._fragments.pop(gid, None)
