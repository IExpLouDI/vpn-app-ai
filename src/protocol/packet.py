import struct

from .messages import Opcode


HEADER_FORMAT = "!B Q"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


def encode_packet(opcode: Opcode, session_id: int, payload: bytes = b"") -> bytes:
    header = struct.pack(HEADER_FORMAT, opcode, session_id)
    return header + payload


def decode_packet(data: bytes) -> tuple[Opcode, int, bytes]:
    if len(data) < HEADER_SIZE:
        raise ValueError(f"Packet too short: {len(data)} < {HEADER_SIZE}")
    opcode_val, session_id = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])
    return Opcode(opcode_val), session_id, data[HEADER_SIZE:]


def encode_ack(session_id: int, packet_ids: list[int]) -> bytes:
    payload = struct.pack(f"!H {len(packet_ids)}I", len(packet_ids), *packet_ids)
    return encode_packet(Opcode.ACK, session_id, payload)


def encode_handshake_message(
    msg_type: int,
    session_id: int,
    payload: bytes,
) -> bytes:
    inner = struct.pack("!B", msg_type) + payload
    return encode_packet(Opcode.CONTROL, session_id, inner)
