import datetime
import socket
import ssl
import threading

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from src.protocol.tls_channel import (
    TLSChannelError,
    TLSControlServer,
    connect_client,
)


def _serve(cert_files, out, err):
    try:
        srv = TLSControlServer(
            "127.0.0.1",
            0,
            str(cert_files / "ca.crt"),
            str(cert_files / "server.crt"),
            str(cert_files / "server.key"),
        )
        out["addr"] = srv.address
        out["event"].set()
        try:
            ch = srv.accept()
            out["accepted_peer"] = ch.peer_common_name
            out["version"] = ch.version
            msg = ch.recv()
            ch.send(b"echo:" + msg)
            out["key"] = ch.exchange_data_key(initiator=False)
            ch.close()
        except ssl.SSLError as e:
            out["rejected"] = str(e)
        srv.close()
    except Exception as e:  # pragma: no cover
        err.append(e)
    finally:
        out["done"].set()


def _client_ctx_no_cert(ca_path, host, port, timeout=5.0):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.maximum_version = ssl.TLSVersion.TLSv1_3
    ctx.load_verify_locations(cafile=ca_path)
    ctx.check_hostname = False
    raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw.settimeout(timeout)
    raw.connect((host, port))
    return ctx.wrap_socket(raw, server_side=False)


def _start(cert_files, out, err):
    out.setdefault("event", threading.Event())
    out.setdefault("done", threading.Event())
    threading.Thread(target=_serve, args=(cert_files, out, err), daemon=True).start()
    assert out["event"].wait(timeout=10)


def test_tls13_control_channel_exchange(cert_files):
    out, err = {}, []
    _start(cert_files, out, err)

    host, port = out["addr"]
    ch = connect_client(
        host,
        port,
        str(cert_files / "ca.crt"),
        str(cert_files / "client.crt"),
        str(cert_files / "client.key"),
    )
    try:
        ch.send(b"hello-control")
        assert ch.recv() == b"echo:hello-control"
        key = ch.exchange_data_key(initiator=True)
        assert ch.recv() == key
        assert len(key) == 32
    finally:
        ch.close()

    assert out["done"].wait(timeout=5)
    assert not err, f"server error: {err}"
    assert out["accepted_peer"] == "Test Client"
    assert out["version"] == "TLSv1.3"
    assert out["key"] == key


def test_server_requires_client_cert(cert_files):
    out, err = {}, []
    _start(cert_files, out, err)

    host, port = out["addr"]
    _client_ctx_no_cert(str(cert_files / "ca.crt"), host, port)

    assert out["done"].wait(timeout=5)
    assert not err, f"server error: {err}"
    assert "accepted_peer" not in out
    assert "rejected" in out


def test_client_rejects_untrusted_ca(cert_files, tmp_path):
    out, err = {}, []
    _start(cert_files, out, err)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    now = datetime.datetime.now(datetime.UTC)
    other_ca = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Other CA")]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Other CA")]))
        .public_key(key.public_key())
        .serial_number(2000)
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256(), default_backend())
    )
    ca_path = tmp_path / "other_ca.crt"
    ca_path.write_bytes(other_ca.public_bytes(serialization.Encoding.PEM))

    host, port = out["addr"]
    with pytest.raises(ssl.SSLError):
        _client_ctx_no_cert(str(ca_path), host, port)

    assert out["done"].wait(timeout=5)


def test_recv_on_closed_channel_raises(cert_files):
    out, err = {}, []
    _start(cert_files, out, err)

    host, port = out["addr"]
    ch = connect_client(
        host,
        port,
        str(cert_files / "ca.crt"),
        str(cert_files / "client.crt"),
        str(cert_files / "client.key"),
    )
    ch.close()
    with pytest.raises(TLSChannelError):
        ch.recv()

    assert out["done"].wait(timeout=5)
