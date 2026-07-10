import pytest

from src.crypto.cipher import Cipher
from src.protocol.data import DataChannel, derive_session_id


class TestDataChannel:
    @pytest.fixture
    def cipher(self):
        return Cipher(Cipher.generate_key())

    @pytest.fixture
    def channel_pair(self, cipher):
        our_id = b"\x01" * 8
        peer_id = b"\x02" * 8
        c1 = DataChannel(our_id, peer_id, cipher)
        c2 = DataChannel(peer_id, our_id, cipher)
        return c1, c2

    def test_derive_session_id(self):
        sid = derive_session_id(b"\x01\x02\x03\x04\x05\x06\x07\x08",
                                b"\x08\x07\x06\x05\x04\x03\x02\x01")
        assert sid == b"\x09\x05\x05\x01\x01\x05\x05\x09"

    def test_encrypt_decrypt(self, channel_pair):
        c1, c2 = channel_pair
        plain = b"\x45\x00\x00\x3c...ip-packet..."
        encrypted = c1.encrypt(plain)
        assert len(encrypted) == 1
        decrypted = c2.decrypt(encrypted[0])
        assert decrypted == plain

    def test_empty_payload(self, channel_pair):
        c1, c2 = channel_pair
        encrypted = c1.encrypt(b"")
        decrypted = c2.decrypt(encrypted[0])
        assert decrypted == b""

    def test_wrong_session_id(self, cipher):
        c1 = DataChannel(b"\x01" * 8, b"\x02" * 8, cipher)
        c2 = DataChannel(b"\xff" * 8, b"\xfe" * 8, cipher)
        plain = b"test data"
        encrypted = c1.encrypt(plain)
        assert c2.decrypt(encrypted[0]) is None

    def test_fragmentation(self, channel_pair):
        c1, c2 = channel_pair
        large = b"x" * 3000
        encrypted = c1.encrypt(large)
        assert len(encrypted) >= 2
        decrypted = b""
        for p in encrypted:
            chunk = c2.decrypt(p)
            if chunk:
                decrypted += chunk
        assert decrypted == large

    def test_tampered_data(self, channel_pair):
        c1, c2 = channel_pair
        plain = b"secret"
        encrypted = bytearray(c1.encrypt(plain)[0])
        encrypted[20] ^= 0xff
        assert c2.decrypt(bytes(encrypted)) is None
