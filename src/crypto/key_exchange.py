from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def generate_ephemeral_keypair() -> tuple[X25519PrivateKey, X25519PublicKey]:
    private = X25519PrivateKey.generate()
    return private, private.public_key()


def private_key_to_bytes(key: X25519PrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )


def public_key_to_bytes(key: X25519PublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def public_key_from_bytes(data: bytes) -> X25519PublicKey:
    return X25519PublicKey.from_public_bytes(data)


def derive_shared_key(
    private_key: X25519PrivateKey,
    peer_public_key: X25519PublicKey,
    salt: bytes = b"pyvpn-key-exchange",
    info: bytes = b"pyvpn-data-channel",
    length: int = 32,
) -> bytes:
    shared = private_key.exchange(peer_public_key)
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=salt,
        info=info,
    )
    return hkdf.derive(shared)
