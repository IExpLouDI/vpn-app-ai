# Architecture as-is

This document describes the repository **as currently implemented**, not the intended
end state. If README and code diverge, this document must be treated as the
authoritative **as-built** description.

## Purpose

The project is an educational VPN prototype inspired by OpenVPN concepts:
virtual tunnel interface, separate control/data concerns, encrypted packet
forwarding, client/server topology.

## Transport

Implemented:

- UDP transport (default) via `asyncio.DatagramProtocol`
  (`src/client.py` `ClientProtocol`, `src/server.py` `ServerProtocol`).
- TCP transport via `asyncio` streams (`asyncio.open_connection` /
  `asyncio.start_server`); every packet is length-prefixed with a 2-byte big-endian
  frame header (`src/protocol/framing.py`).
- Both transports share one packet handler (`handle_udp_data` on both sides —
  the name is historical; it handles TCP frames too).

Assumptions: IPv4 only; server listens on `0.0.0.0`.

## Control plane

Implemented (`src/protocol/control.py`):

- Custom handshake over the same UDP/TCP socket, packet header
  `[Opcode (1)] [SessionID (8)] [Payload]` (`src/protocol/packet.py`).
- Sequence: `HARD_RESET_CLIENT` → `HARD_RESET_SERVER` → `CLIENT_HELLO`
  (cert + ephemeral X25519 pubkey) → `SERVER_HELLO` (cert + pubkey + signature)
  → `CLIENT_FINISHED` (signature) → `ESTABLISHED`.
- Key derivation: X25519 ECDH + HKDF-SHA256, salt = order-independent
  concatenation of both session IDs, info = `pyvpn-data-channel`
  (`src/crypto/key_exchange.py`).
- Auth mode: if `ca`/`cert`/`key` are configured, the peer certificate must
  chain to the CA and handshake signatures are verified
  (`_verify_peer_cert`, `_sign`, `_verify`).
- Dev mode: if no CA is configured, empty certificates are accepted and
  signature checks are skipped. Mixed mode fails closed: a peer with a CA
  rejects a certless counterpart (tests: `test_auth_server_rejects_certless_client`,
  `test_auth_client_rejects_certless_server`).
- After establishment the server assigns a virtual IP (`IP_ASSIGN`) from the
  pool and installs a host route to it.

Experimental (not the runtime path): mutual TLS 1.3 control channel over TCP
(`src/protocol/tls_channel.py`), covered by `tests/test_tls_channel.py`.

Not implemented: handshake DoS/rate limiting, key renegotiation, `SHUTDOWN`
message (defined in `src/protocol/messages.py`, never sent).

## Data plane

Implemented (`src/protocol/data.py`, `src/crypto/cipher.py`):

- AES-256-GCM per packet; random 12-byte nonce per encryption; AAD =
  `SharedSessionID + PacketID`; `SharedSessionID = client_id XOR server_id`.
- Wire payload: `[PacketID (4)] [Nonce (12)] [Ciphertext] [Tag (16)]`;
  plaintext inside starts with a 1-byte compression marker
  (0 = none, 1 = LZ4) or `0x80`-flagged fragment header `[Total][Index]`.
- Fragmentation/reassembly for payloads > 1400 bytes, 5 s fragment-group
  timeout (`FRAG_TIMEOUT`); interface MTU set to 1500.
- Optional LZ4 compression, opt-in via `comp-lzo`; self-describing per packet
  (receiver needs only the `lz4` library, not the flag).
- Replay protection: 64-packet sliding-bitmap window
  (`src/protocol/replay.py`) checked before decryption.

## OS integration

Implemented (Linux; Windows TUN-only via `src/tun_windows.py`):

- TUN lifecycle: open `/dev/net/tun` + `ioctl(TUNSETIFF)`, `ip addr`,
  `ip link set up/mtu`, delete on close (`src/tun.py`). Requires
  `CAP_NET_ADMIN`/root.
- Server startup: `enable_ip_forward()` (writes `1` to
  `/proc/sys/net/ipv4/ip_forward`), route to the VPN subnet, NAT
  (`iptables -t nat -A POSTROUTING -s <vpn-net> -o <default-iface> -j MASQUERADE`,
  interface auto-detected from the default route). NAT rule is removed on
  shutdown (`teardown_nat`). Requires root + `iptables`.
- Per-client host routes (`ip route add <client-ip>/32 dev tun`) need root;
  with `--user` (privilege drop at startup) they fail silently — privilege
  separation is therefore partial (`src/privileges.py`).
- Client: sets assigned IP on TUN, adds subnet route, optional default route
  (`redirect-gateway`), drops privileges afterwards if `--user` given.
- Status file: client-only (`src/status.py`), OpenVPN-status-v2-like text,
  written every 10 s and on connect; deleted on exit.

## Failure handling

- Keepalive: server sends `KEEPALIVE` every `keepalive_interval` (default 10 s)
  to established clients; client echoes it back. Any inbound packet refreshes
  the peer's `last_seen`.
- Timeout: server drops clients silent for `keepalive_timeout` (default 120 s)
  and unfinished handshakes after 30 s (`HANDSHAKE_TIMEOUT`); client tears down
  and reconnects after the same timeout.
- Reconnect: client retries every 5 s indefinitely until stopped
  (`VpnClient.run` loop); TUN device is reused across attempts.
- Shutdown: signal handlers (SIGINT/SIGTERM) stop the loops; cleanup removes
  routes, NAT rule, per-client routes, and closes sockets/TUN. No `SHUTDOWN`
  message is sent — the peer learns via keepalive timeout.

## Constraints

- Linux is the only fully supported platform; Windows is TUN-only
  (no routing/NAT/privilege drop); macOS/BSD unsupported.
- Privileged operations: TUN open/config, `ip route`, `iptables`,
  `/proc/sys/net/ipv4/ip_forward`.
- Security properties and their test evidence are listed in
  [`SECURITY_MODEL.md`](SECURITY_MODEL.md); implementation status per feature in
  [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md).
