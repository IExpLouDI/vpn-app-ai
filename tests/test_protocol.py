import struct

import pytest

from src.protocol.framing import frame_packet
from src.protocol.messages import MessageType, Opcode
from src.protocol.packet import (
    decode_packet,
    encode_ack,
    encode_handshake_message,
    encode_packet,
)


class TestPacket:
    def test_encode_decode_roundtrip(self):
        payload = b"hello"
        data = encode_packet(Opcode.DATA, 12345, payload)
        opcode, sid, rest = decode_packet(data)
        assert opcode == Opcode.DATA
        assert sid == 12345
        assert rest == payload

    def test_decode_short_packet(self):
        with pytest.raises(ValueError, match="Packet too short"):
            decode_packet(b"\x01")

    def test_encode_ack(self):
        data = encode_ack(42, [1, 2, 3])
        opcode, sid, payload = decode_packet(data)
        assert opcode == Opcode.ACK
        assert sid == 42
        count = struct.unpack("!H", payload[:2])[0]
        ids = struct.unpack(f"!{count}I", payload[2:])
        assert list(ids) == [1, 2, 3]

    def test_encode_handshake_message(self):
        inner = b"\x01\x02\x03"
        data = encode_handshake_message(MessageType.CLIENT_HELLO, 99, inner)
        opcode, sid, payload = decode_packet(data)
        assert opcode == Opcode.CONTROL
        assert sid == 99
        assert payload[0] == MessageType.CLIENT_HELLO
        assert payload[1:] == inner

    def test_empty_payload(self):
        data = encode_packet(Opcode.CONTROL, 0)
        opcode, sid, rest = decode_packet(data)
        assert opcode == Opcode.CONTROL
        assert sid == 0
        assert rest == b""

    def test_large_payload(self):
        payload = b"x" * 65535
        data = encode_packet(Opcode.DATA, 1, payload)
        _, _, rest = decode_packet(data)
        assert len(rest) == 65535


class TestFraming:
    def test_frame_packet(self):
        data = frame_packet(b"hello")
        assert len(data) == 2 + 5
        length = struct.unpack("!H", data[:2])[0]
        assert length == 5
        assert data[2:] == b"hello"
