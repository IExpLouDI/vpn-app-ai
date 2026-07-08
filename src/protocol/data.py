import struct
import logging

from .messages import Opcode
from .packet import encode_packet, decode_packet
from ..crypto.cipher import Cipher

logger = logging.getLogger("pyvpn.protocol.data")


def derive_session_id(our_id: bytes, peer_id: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(our_id, peer_id))


class DataChannel:
    def __init__(self, our_id: bytes, peer_id: bytes, cipher: Cipher):
        self.shared_id = derive_session_id(our_id, peer_id)
        self.cipher = cipher
        self.packet_counter = 0

    def encrypt(self, plaintext: bytes) -> bytes:
        self.packet_counter += 1
        counter_bytes = struct.pack("!I", self.packet_counter)
        aad = self.shared_id + counter_bytes
        encrypted = self.cipher.encrypt(plaintext, aad)
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
            plaintext = self.cipher.decrypt(encrypted, aad)
            return plaintext
        except Exception as e:
            logger.warning("Decryption failed: %s", e)
            return None
