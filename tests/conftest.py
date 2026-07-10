import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.backends import default_backend
import datetime


def _make_self_signed_cert(key, subject_name: str) -> x509.Certificate:
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, subject_name),
    ])
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(1000)
        .not_valid_before(datetime.datetime.utcnow() - datetime.timedelta(days=1))
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256(), default_backend())
    )


def _make_cert(ca_key, ca_cert, subject_key, subject_name: str) -> x509.Certificate:
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, subject_name),
    ])
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(subject_key.public_key())
        .serial_number(1001)
        .not_valid_before(datetime.datetime.utcnow() - datetime.timedelta(days=1))
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        )
        .sign(ca_key, hashes.SHA256(), default_backend())
    )


@pytest.fixture(scope="session")
def ca_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())


@pytest.fixture(scope="session")
def ca_cert(ca_key):
    return _make_self_signed_cert(ca_key, "Test CA")


@pytest.fixture(scope="session")
def server_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())


@pytest.fixture(scope="session")
def server_cert(ca_key, ca_cert, server_key):
    return _make_cert(ca_key, ca_cert, server_key, "Test Server")


@pytest.fixture(scope="session")
def client_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())


@pytest.fixture(scope="session")
def client_cert(ca_key, ca_cert, client_key):
    return _make_cert(ca_key, ca_cert, client_key, "Test Client")


@pytest.fixture
def ca_pem(ca_cert):
    return ca_cert.public_bytes(serialization.Encoding.PEM)


@pytest.fixture
def server_cert_pem(server_cert):
    return server_cert.public_bytes(serialization.Encoding.PEM)


@pytest.fixture
def server_key_pem(server_key):
    return server_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )


@pytest.fixture
def client_cert_pem(client_cert):
    return client_cert.public_bytes(serialization.Encoding.PEM)


@pytest.fixture
def client_key_pem(client_key):
    return client_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )


@pytest.fixture
def cert_files(tmp_path, ca_pem, server_cert_pem, server_key_pem, client_cert_pem, client_key_pem):
    d = tmp_path / "certs"
    d.mkdir()
    (d / "ca.crt").write_bytes(ca_pem)
    (d / "server.crt").write_bytes(server_cert_pem)
    (d / "server.key").write_bytes(server_key_pem)
    (d / "client.crt").write_bytes(client_cert_pem)
    (d / "client.key").write_bytes(client_key_pem)
    return d
