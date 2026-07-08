import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class Cipher:
    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError(f"AES-256 requires 32-byte key, got {len(key)}")
        self._cipher = AESGCM(key)

    @classmethod
    def generate_key(cls) -> bytes:
        return AESGCM.generate_key(bit_length=256)

    def encrypt(self, plaintext: bytes, aad: bytes | None = None) -> bytes:
        nonce = os.urandom(12)
        ciphertext = self._cipher.encrypt(nonce, plaintext, aad or b"")
        return nonce + ciphertext

    def decrypt(self, data: bytes, aad: bytes | None = None) -> bytes:
        if len(data) < 12:
            raise ValueError("Ciphertext too short")
        nonce = data[:12]
        ciphertext = data[12:]
        return self._cipher.decrypt(nonce, ciphertext, aad or b"")
