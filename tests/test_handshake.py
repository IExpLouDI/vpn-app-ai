"""End-to-end test of the VPN handshake and data channel."""
import os
import sys

os.chdir(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.getcwd())

from src.protocol.control import (
    Session, client_start_handshake, client_handle_reset_ack,
    client_handle_server_hello, server_handle_reset,
    server_handle_client_hello, server_handle_client_finished,
)
from src.protocol.packet import decode_packet


def main():
    server_session = Session(is_server=True)
    server_session.configure("certs/ca.crt", "certs/server.crt", "certs/server.key")

    client_session = Session(is_server=False)
    client_session.configure("certs/ca.crt", "certs/client.crt", "certs/client.key")

    # Step 1: Client sends HARD_RESET
    c1 = client_start_handshake(client_session)
    assert len(c1) == 1
    print("1: Client HARD_RESET -> OK")

    # Step 2: Server responds with HARD_RESET_SERVER
    s1 = server_handle_reset(server_session, c1[0])
    assert len(s1) == 1
    print("2: Server HARD_RESET_ACK -> OK")

    # Step 3: Client handles ACK, sends CLIENT_HELLO
    c2 = client_handle_reset_ack(client_session, s1[0])
    assert len(c2) == 1
    _, _, payload = decode_packet(c2[0])
    print("3: Client CLIENT_HELLO -> OK (msg_type=%d, body_len=%d)" % (payload[0], len(payload) - 1))

    # Step 4: Server handles CLIENT_HELLO, sends SERVER_HELLO
    s2 = server_handle_client_hello(server_session, payload[1:])
    assert len(s2) == 1, "Server should reply with SERVER_HELLO"
    _, _, payload2 = decode_packet(s2[0])
    print("4: Server SERVER_HELLO -> OK (msg_type=%d, body_len=%d)" % (payload2[0], len(payload2) - 1))

    # Step 5: Client handles SERVER_HELLO, sends CLIENT_FINISHED
    c3 = client_handle_server_hello(client_session, payload2[1:])
    assert len(c3) == 1, "Client should reply with FINISHED, got %d" % len(c3)
    _, _, payload3 = decode_packet(c3[0])
    print("5: Client CLIENT_FINISHED -> OK (msg_type=%d)" % payload3[0])

    # Step 6: Server handles CLIENT_FINISHED
    s3 = server_handle_client_finished(server_session, payload3[1:])
    print("6: Server FINISHED -> OK (%d packets)" % len(s3))

    assert client_session.is_established, "Client not ESTABLISHED"
    assert server_session.is_established, "Server not ESTABLISHED"
    assert client_session.cipher is not None, "Client has no cipher"
    assert server_session.cipher is not None, "Server has no cipher"

    print("\nBoth sides ESTABLISHED with matching ciphers")

    # Test data channel roundtrip
    from src.protocol.data import DataChannel

    c_dc = DataChannel(client_session.session_id, client_session.peer_session_id or b"", client_session.cipher)
    s_dc = DataChannel(server_session.session_id, server_session.peer_session_id or b"", server_session.cipher)

    plain = b"\x45\x00\x00\x2e...mock-ip-packet"
    encrypted = c_dc.encrypt(plain)
    decrypted = s_dc.decrypt(encrypted)

    assert decrypted == plain, "Data channel roundtrip mismatch"
    print("Data channel roundtrip: %dB plain -> %dB wire -> OK" % (len(plain), len(encrypted)))

    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    main()
