"""Debug data channel key mismatch."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.protocol.control import (
    Session, client_start_handshake, client_handle_reset_ack,
    client_handle_server_hello, server_handle_reset,
    server_handle_client_hello, server_handle_client_finished,
)
from src.protocol.packet import decode_packet
from src.protocol.data import DataChannel

ss = Session(is_server=True)
ss.configure("certs/ca.crt", "certs/server.crt", "certs/server.key")

cs = Session(is_server=False)
cs.configure("certs/ca.crt", "certs/client.crt", "certs/client.key")

c1 = client_start_handshake(cs)
s1 = server_handle_reset(ss, c1[0])
c2 = client_handle_reset_ack(cs, s1[0])
_, _, p = decode_packet(c2[0])
s2 = server_handle_client_hello(ss, p[1:])
_, _, p2 = decode_packet(s2[0])
c3 = client_handle_server_hello(cs, p2[1:])
_, _, p3 = decode_packet(c3[0])
s3 = server_handle_client_finished(ss, p3[1:])

print("Server session_id:     ", ss.session_id.hex())
print("Server peer_session_id:", (ss.peer_session_id or b"").hex())
print("Client session_id:     ", cs.session_id.hex())
print("Client peer_session_id:", (cs.peer_session_id or b"").hex())

s_dc = DataChannel(ss.session_id, ss.peer_session_id or b"", ss.cipher)
c_dc = DataChannel(cs.session_id, cs.peer_session_id or b"", cs.cipher)

print("Server shared_id:      ", s_dc.shared_id.hex())
print("Client shared_id:      ", c_dc.shared_id.hex())

plain = b"test-packet-data-1234"

# Try cross-cipher (checks if keys match)
ct = cs.cipher.encrypt(plain)
pt = ss.cipher.decrypt(ct)
print("Cross-cipher test (client->server):", "OK" if pt == plain else "FAIL")

ct2 = ss.cipher.encrypt(plain)
pt2 = cs.cipher.decrypt(ct2)
print("Cross-cipher test (server->client):", "OK" if pt2 == plain else "FAIL")

enc = c_dc.encrypt(plain)
dec = s_dc.decrypt(enc)
print("Encrypted len:", len(enc))
print("Decrypted len:", len(dec) if dec else 0)
if dec == plain:
    print("SUCCESS: roundtrip OK")
else:
    print("FAIL: mismatch")
    if dec is None:
        print("  dec is None (decryption failed)")
    else:
        print("  got:", dec)
        print("  exp:", plain)
