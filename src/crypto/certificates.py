from pathlib import Path

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa, padding
from cryptography.x509.oid import NameOID


def load_certificate(path: str | Path) -> x509.Certificate:
    path = Path(path)
    data = path.read_bytes()
    return x509.load_pem_x509_certificate(data, default_backend())


def load_private_key(path: str | Path, password: bytes | None = None):
    path = Path(path)
    data = path.read_bytes()
    return serialization.load_pem_private_key(data, password, default_backend())


def verify_certificate(
    cert: x509.Certificate,
    ca_cert: x509.Certificate,
) -> bool:
    try:
        ca_public_key = ca_cert.public_key()
        if isinstance(ca_public_key, rsa.RSAPublicKey):
            ca_public_key.verify(
                cert.signature,
                cert.tbs_certificate_bytes,
                padding.PKCS1v15(),
                cert.signature_hash_algorithm,
            )
        elif isinstance(ca_public_key, ec.EllipticCurvePublicKey):
            ca_public_key.verify(
                cert.signature,
                cert.tbs_certificate_bytes,
                ec.ECDSA(cert.signature_hash_algorithm),
            )
        else:
            return False
        return True
    except Exception:
        return False


def get_cert_common_name(cert: x509.Certificate) -> str:
    try:
        return cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    except IndexError:
        return ""


def get_peer_public_key_bytes(cert: x509.Certificate) -> bytes:
    pub_key = cert.public_key()
    if isinstance(pub_key, ec.EllipticCurvePublicKey):
        return pub_key.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
    return pub_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def get_cert_fingerprint(cert: x509.Certificate) -> str:
    return cert.fingerprint(hashes.SHA256()).hex()
