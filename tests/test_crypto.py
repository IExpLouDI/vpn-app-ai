import pytest
from cryptography.hazmat.primitives import serialization

from src.crypto.certificates import (
    get_cert_common_name,
    get_cert_fingerprint,
    load_certificate,
    load_private_key,
    verify_certificate,
)
from src.crypto.cipher import Cipher
from src.crypto.key_exchange import (
    derive_shared_key,
    generate_ephemeral_keypair,
    public_key_from_bytes,
    public_key_to_bytes,
)


class TestCipher:
    def test_encrypt_decrypt(self):
        key = Cipher.generate_key()
        cipher = Cipher(key)
        plaintext = b"hello, vpn!"
        encrypted = cipher.encrypt(plaintext)
        assert encrypted != plaintext
        decrypted = cipher.decrypt(encrypted)
        assert decrypted == plaintext

    def test_encrypt_decrypt_with_aad(self):
        key = Cipher.generate_key()
        cipher = Cipher(key)
        plaintext = b"secret data"
        aad = b"additional authenticated data"
        encrypted = cipher.encrypt(plaintext, aad)
        decrypted = cipher.decrypt(encrypted, aad)
        assert decrypted == plaintext

    def test_decrypt_wrong_key(self):
        key1 = Cipher.generate_key()
        key2 = Cipher.generate_key()
        cipher1 = Cipher(key1)
        cipher2 = Cipher(key2)
        plaintext = b"test"
        encrypted = cipher1.encrypt(plaintext)
        with pytest.raises(Exception):
            cipher2.decrypt(encrypted)

    def test_decrypt_tampered(self):
        key = Cipher.generate_key()
        cipher = Cipher(key)
        encrypted = bytearray(cipher.encrypt(b"test"))
        encrypted[20] ^= 1
        with pytest.raises(Exception):
            cipher.decrypt(bytes(encrypted))

    def test_key_length_validation(self):
        with pytest.raises(ValueError, match="AES-256 requires 32-byte key"):
            Cipher(b"too-short")

    def test_ciphertext_too_short(self):
        key = Cipher.generate_key()
        cipher = Cipher(key)
        with pytest.raises(ValueError):
            cipher.decrypt(b"short")


class TestKeyExchange:
    def test_ecdh_key_agreement(self):
        sk1, pk1 = generate_ephemeral_keypair()
        sk2, pk2 = generate_ephemeral_keypair()
        shared1 = derive_shared_key(sk1, pk2)
        shared2 = derive_shared_key(sk2, pk1)
        assert shared1 == shared2
        assert len(shared1) == 32

    def test_ecdh_with_salt(self):
        sk1, pk1 = generate_ephemeral_keypair()
        sk2, pk2 = generate_ephemeral_keypair()
        salt = b"test-salt"
        shared1 = derive_shared_key(sk1, pk2, salt=salt)
        shared2 = derive_shared_key(sk2, pk1, salt=salt)
        assert shared1 == shared2

    def test_public_key_serialization(self):
        _, pk = generate_ephemeral_keypair()
        pk_bytes = public_key_to_bytes(pk)
        pk_restored = public_key_from_bytes(pk_bytes)
        assert pk_restored.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        ) == pk_bytes

    def test_different_keys(self):
        sk1, pk1 = generate_ephemeral_keypair()
        sk2, pk2 = generate_ephemeral_keypair()
        a = derive_shared_key(sk1, pk2)
        b = derive_shared_key(sk1, pk1)
        assert a != b


class TestCertificates:
    def test_load_certificate(self, cert_files):
        cert = load_certificate(str(cert_files / "ca.crt"))
        assert cert is not None
        assert get_cert_common_name(cert) == "Test CA"

    def test_load_private_key(self, cert_files):
        key = load_private_key(str(cert_files / "server.key"))
        assert key is not None

    def test_verify_chain(self, cert_files):
        ca = load_certificate(str(cert_files / "ca.crt"))
        server = load_certificate(str(cert_files / "server.crt"))
        assert verify_certificate(server, ca) is True

    def test_reject_self_signed(self, cert_files):
        client = load_certificate(str(cert_files / "client.crt"))
        assert verify_certificate(client, client) is False

    def test_fingerprint(self, cert_files):
        cert = load_certificate(str(cert_files / "ca.crt"))
        fp = get_cert_fingerprint(cert)
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)
