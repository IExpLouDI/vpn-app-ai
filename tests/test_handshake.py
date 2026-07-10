import pytest

from src.protocol.control import (
    Session,
    client_handle_reset_ack,
    client_handle_server_hello,
    client_start_handshake,
    server_handle_client_finished,
    server_handle_client_hello,
    server_handle_reset,
)
from src.protocol.data import DataChannel
from src.protocol.packet import decode_packet


class TestHandshake:
    def test_full_handshake(self, cert_files):
        ca = str(cert_files / "ca.crt")
        server_crt = str(cert_files / "server.crt")
        server_key = str(cert_files / "server.key")
        client_crt = str(cert_files / "client.crt")
        client_key = str(cert_files / "client.key")

        server_session = Session(is_server=True)
        server_session.configure(ca, server_crt, server_key)

        client_session = Session(is_server=False)
        client_session.configure(ca, client_crt, client_key)

        # Step 1: Client sends HARD_RESET
        c1 = client_start_handshake(client_session)
        assert len(c1) == 1

        # Step 2: Server responds with HARD_RESET_SERVER
        s1 = server_handle_reset(server_session, c1[0])
        assert len(s1) == 1

        # Step 3: Client sends CLIENT_HELLO
        c2 = client_handle_reset_ack(client_session, s1[0])
        assert len(c2) == 1
        _, _, payload = decode_packet(c2[0])

        # Step 4: Server sends SERVER_HELLO
        s2 = server_handle_client_hello(server_session, payload[1:])
        assert len(s2) == 1
        _, _, payload2 = decode_packet(s2[0])

        # Step 5: Client sends CLIENT_FINISHED
        c3 = client_handle_server_hello(client_session, payload2[1:])
        assert len(c3) == 1
        _, _, payload3 = decode_packet(c3[0])

        # Step 6: Server verifies FINISHED
        s3 = server_handle_client_finished(server_session, payload3[1:])
        assert len(s3) == 0

        assert client_session.is_established
        assert server_session.is_established
        assert client_session.cipher is not None
        assert server_session.cipher is not None

    def test_data_channel_roundtrip(self, cert_files):
        ca = str(cert_files / "ca.crt")
        server_crt = str(cert_files / "server.crt")
        server_key = str(cert_files / "server.key")
        client_crt = str(cert_files / "client.crt")
        client_key = str(cert_files / "client.key")

        server_session = Session(is_server=True)
        server_session.configure(ca, server_crt, server_key)

        client_session = Session(is_server=False)
        client_session.configure(ca, client_crt, client_key)

        c1 = client_start_handshake(client_session)
        s1 = server_handle_reset(server_session, c1[0])
        c2 = client_handle_reset_ack(client_session, s1[0])
        _, _, payload = decode_packet(c2[0])
        s2 = server_handle_client_hello(server_session, payload[1:])
        _, _, payload2 = decode_packet(s2[0])
        c3 = client_handle_server_hello(client_session, payload2[1:])
        _, _, payload3 = decode_packet(c3[0])
        server_handle_client_finished(server_session, payload3[1:])

        c_dc = DataChannel(
            client_session.session_id,
            client_session.peer_session_id or b"",
            client_session.cipher,
        )
        s_dc = DataChannel(
            server_session.session_id,
            server_session.peer_session_id or b"",
            server_session.cipher,
        )

        plain = b"\x45\x00\x00\x2e...mock-ip-packet"
        encrypted = c_dc.encrypt(plain)
        decrypted = s_dc.decrypt(encrypted[0])

        assert decrypted == plain

    def test_handshake_reject_bad_cert(self, cert_files, tmp_path):
        import datetime
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        ca = str(cert_files / "ca.crt")
        server_crt = str(cert_files / "server.crt")
        server_key = str(cert_files / "server.key")

        wrong_key = rsa.generate_private_key(65537, 2048, default_backend())
        wrong_cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Evil Client")]))
            .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Evil Client")]))
            .public_key(wrong_key.public_key())
            .serial_number(999)
            .not_valid_before(datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1))
            .not_valid_after(datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(wrong_key, hashes.SHA256(), default_backend())
        )
        wrong_cert_path = tmp_path / "evil.crt"
        wrong_key_path = tmp_path / "evil.key"
        wrong_cert_path.write_bytes(wrong_cert.public_bytes(serialization.Encoding.PEM))
        wrong_key_path.write_bytes(
            wrong_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )

        server_session = Session(is_server=True)
        server_session.configure(ca, server_crt, server_key)

        client_session = Session(is_server=False)
        client_session.configure(ca, str(wrong_cert_path), str(wrong_key_path))

        c1 = client_start_handshake(client_session)
        s1 = server_handle_reset(server_session, c1[0])
        c2 = client_handle_reset_ack(client_session, s1[0])
        _, _, payload = decode_packet(c2[0])
        s2 = server_handle_client_hello(server_session, payload[1:])
        assert len(s2) == 0, "Server should reject client cert not signed by CA"
