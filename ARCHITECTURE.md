# Python VPN Application — Architecture & Development Plan

## Overview

A minimal but functional VPN implementation in Python, inspired by OpenVPN's architecture. The application creates a secure tunnel between a client and server, forwarding IP packets through an encrypted UDP connection.

> **Note:** This is an educational project. It implements core OpenVPN concepts (TUN interface, control/data channel separation, TLS authentication, AES-GCM encryption) but is not intended for production use.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────┐
│                    VPN Client                        │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │ TUN/TAP  │  │  Packet  │  │  Control Channel  │  │
│  │ Interface│◄─┤  Router  │◄─┤  (TLS + Auth)     │  │
│  │  (dev)   │  │          │  │                   │  │
│  └────▲─────┘  └────▲─────┘  └────────▲──────────┘  │
│       │              │                 │             │
│  ┌────┴──────────────┴─────────────────┴──────────┐  │
│  │           Data Channel (AES-GCM)                │  │
│  │           UDP Transport                         │  │
│  └───────────────────▲────────────────────────────┘  │
│                      │ UDP (encrypted packets)       │
├──────────────────────┼──────────────────────────────┤
│                 Internet 🔒                          │
├──────────────────────┼──────────────────────────────┤
│                      ▼                              │
│  ┌───────────────────┴────────────────────────────┐  │
│  │           Data Channel (AES-GCM)                │  │
│  │           UDP Transport                         │  │
│  └───────────────────▲────────────────────────────┘  │
│       │              │                 │             │
│  ┌────▼──────────────┴─────────────────▼──────────┐  │
│  │ TUN/TAP  │  Packet  │  Control Channel  │  Auth  │  │
│  │ Interface│  Router  │  (TLS + Cert)     │  PEM   │  │
│  └──────────┘  └──────────┘  └───────────────────┘  │
│                    VPN Server                        │
└─────────────────────────────────────────────────────┘
```

### Two-Channel Design (OpenVPN-inspired)

| Channel        | Purpose                               | Protocol         | Encryption              |
|----------------|---------------------------------------|------------------|-------------------------|
| Control Channel | Handshake, auth, key exchange         | TLS 1.3 over UDP | X.509 certificates      |
| Data Channel    | IP packet tunneling                   | AES-256-GCM      | Symmetric session keys  |

Both channels are multiplexed over a single UDP connection using a lightweight frame header.

---

## Core Components

### 1. TUN Interface Manager — `tun.py`

Creates and manages the virtual TUN network interface.

- Opens `/dev/net/tun` via `open()` + `fcntl.ioctl(TUNSETIFF)`
- Reads raw IP packets from the interface
- Writes decrypted IP packets into the interface
- Configures IP address and MTU via `ioctl(SIOCSIFADDR)` or subprocess calls to `ip`
- Handles interface lifecycle (create, configure, destroy)

**Interface:** `TunInterface(dev_name="tun0")` — context manager

```python
with TunInterface("tun0") as tun:
    tun.set_ip("10.8.0.2/24")
    tun.set_mtu(1500)
    packet = tun.read()     # blocks until packet arrives
    tun.write(packet)
```

### 2. Control Channel — `protocol/control.py`

Manages the secure control channel — handshake, authentication, key exchange, keep-alive.

**Handshake sequence (simplified):**
1. Client sends `P_CONTROL_HARD_RESET_CLIENT_V2`
2. Server responds `P_CONTROL_HARD_RESET_SERVER_V2`
3. TLS handshake begins (Client Hello → Server Hello → Certificates → Finished)
4. Mutual certificate verification (mTLS)
5. Session key derivation from TLS keying material (via `export_keying_material`)
6. Periodic `P_CONTROL_KEEPALIVE` to maintain session

**Packet format:**
```
[Opcode (1)] [KeyID (1)] [SessionID (8)] [Payload]
```

### 3. Data Channel — `protocol/data.py`

Encrypts and tunnels IP packets.

- Reads raw IP packet from TUN interface
- Compresses payload (optional, LZ4)
- Encrypts with AES-256-GCM using session key
- Wraps in data frame header
- Sends over UDP to peer
- Peer decrypts → decompresses → writes to its TUN interface

**Data frame format:**
```
[SessionID (4)] [PacketID (4)] [Nonce (12)] [Ciphertext...] [Tag (16)]
```

### 4. Crypto Module — `crypto/`

| File               | Responsibility                                      |
|--------------------|-----------------------------------------------------|
| `tls.py`           | TLS wrapper — wraps `ssl.SSLContext` for mTLS       |
| `cipher.py`        | AES-256-GCM encrypt/decrypt, key import             |
| `certificates.py`  | Load/generate X.509 certs, verify chain             |
| `key_exchange.py`  | ECDH (X25519) for PFS, key derivation (HKDF)        |

### 5. Authentication — `auth/cert_auth.py`

Mutual TLS (mTLS) certificate verification.

- Server verifies client certificate is signed by trusted CA
- Client verifies server certificate is signed by trusted CA
- Optional: username/password authentication on top of mTLS
- Certificate revocation checking (optional)

### 6. Configuration — `config.py`

Parses OpenVPN-style configuration files.

**Supported directives:**
```
dev tun
proto udp
port 1194
ca ca.crt
cert server.crt
key server.key
server 10.8.0.0 255.255.255.0
ifconfig-pool 10.8.0.2 10.8.0.100
cipher AES-256-GCM
comp-lzo
keepalive 10 120
verb 3
```

Returns a `Config` dataclass with typed fields.

### 7. Routing — `routing.py`

Manages system routing and NAT rules.

- Adds route to VPN subnet via TUN interface
- Pushes client-specific routes from server
- Manages `iptables` MASQUERADE rule for NAT
- Optionally redirects all traffic (default gateway) through VPN

### 8. Server — `server.py`

Multi-client VPN server using `asyncio`.

- Accepts incoming UDP connections
- Manages client sessions (handshake → data → disconnect)
- Virtual IP allocation pool (`ifconfig-pool`)
- Routes traffic between clients and LAN
- Connection timeout and cleanup

### 9. Client — `client.py`

VPN client.

- Resolves server hostname
- Initiates control channel handshake
- Configures local TUN interface with assigned IP
- Reads/writes encrypted packets bidirectionally
- Automatic reconnection on timeout

---

## Technology Stack

| Component       | Library              | Rationale                           |
|-----------------|----------------------|-------------------------------------|
| TUN/TAP         | `fcntl` (stdlib)     | Direct kernel interface, minimal    |
| TLS             | `ssl` (stdlib)       | Built-in OpenSSL wrapper            |
| X.509 certs     | `cryptography`       | Load/verify PEM certificates        |
| AES-256-GCM     | `cryptography`       | Authenticated encryption, safe API  |
| X25519/ECDH     | `cryptography`       | Key exchange for PFS                |
| Async I/O       | `asyncio` (stdlib)   | Single-threaded concurrency         |
| Config parser   | `configparser`       | INI-like format                     |
| Compression     | `lz4`                | Fast, optional data compression     |
| Packet parsing  | `construct`          | Declarative binary protocol          |
| CLI             | `argparse` (stdlib)  | Command-line arguments              |

---

## Project Structure

```
vpn-app/
├── README.md
├── ARCHITECTURE.md
├── requirements.txt
├── setup.py
├── examples/
│   ├── server.conf
│   └── client.conf
├── certs/                          # Certificate generation
│   ├── generate.sh                 #   openssl wrapper
│   └── openssl.cnf
├── src/
│   ├── __init__.py
│   ├── app.py                      # Entry point
│   ├── cli.py                      # CLI argument parsing
│   ├── config.py                   # Config file parser
│   ├── tun.py                      # TUN interface
│   ├── server.py                   # VPN server
│   ├── client.py                   # VPN client
│   ├── routing.py                  # Routing & iptables
│   ├── compression.py              # LZ4 wrapper
│   ├── utils.py                    # Helpers
│   ├── crypto/
│   │   ├── __init__.py
│   │   ├── tls.py                  # TLS session
│   │   ├── cipher.py               # AES-256-GCM
│   │   ├── certificates.py         # Load/verify certs
│   │   └── key_exchange.py         # ECDH + HKDF
│   ├── protocol/
│   │   ├── __init__.py
│   │   ├── control.py              # Control channel
│   │   ├── data.py                 # Data channel
│   │   ├── packet.py               # Binary packet format
│   │   └── messages.py             # Message opcodes
│   └── auth/
│       ├── __init__.py
│       └── cert_auth.py            # Certificate auth
└── tests/
    ├── __init__.py
    ├── test_tun.py
    ├── test_crypto.py
    ├── test_protocol.py
    └── test_integration.py
```

---

## Development Phases

### Phase 1 — Tunnel Foundation

Goal: raw UDP tunnel with TUN interface (no encryption).

**Tasks:**
- [ ] Scaffold project structure, `setup.py`, `requirements.txt`
- [ ] Implement `tun.py` — TUN device create/read/write/destroy
- [ ] Implement basic UDP client/server with packet forwarding
- [ ] Implement `cli.py` + `config.py`
- [ ] Test: two machines can ping through raw tunnel

**Deliverable:** `sudo python -m src.app client --remote 192.168.1.100` forwards pings.

### Phase 2 — Encryption

Goal: authenticated, encrypted tunnel with key exchange.

**Tasks:**
- [ ] Certificate generation script (CA, server, client via openssl)
- [ ] `crypto/certificates.py` — load and verify PEM certs
- [ ] `crypto/tls.py` — TLS handshake over our UDP framing
- [ ] `protocol/control.py` — handshake sequence with mTLS
- [ ] `crypto/key_exchange.py` — X25519 + HKDF for PFS
- [ ] `crypto/cipher.py` — AES-256-GCM encrypt/decrypt
- [ ] `protocol/data.py` — encrypted data channel
- [ ] Test: Wireshark on tunnel shows only encrypted UDP

**Deliverable:** pings go through, but the UDP stream is encrypted with forward secrecy.

### Phase 3 — Multi-Client Server & Routing

Goal: server handles multiple clients, pushes routes, NAT.

**Tasks:**
- [ ] `server.py` — asyncio-based multi-client acceptor
- [ ] Virtual IP pool (`ifconfig-pool`)
- [ ] Per-client session state machine
- [ ] `routing.py` — push routes to clients
- [ ] NAT via iptables MASQUERADE
- [ ] Redirect-gateway option
- [ ] Test: 3+ clients connected, can ping each other via VPN

**Deliverable:** multi-client VPN server with LAN access.

### Phase 4 — Production Polish

Goal: stable, resilient, well-behaved application.

**Tasks:**
- [ ] Keep-alive with configurable interval
- [ ] Auto-reconnect on timeout
- [ ] Graceful shutdown (SIGTERM, SIGINT handlers)
- [ ] Structured logging (module-level loggers)
- [ ] LZ4 compression option
- [ ] Packet fragmentation for large payloads
- [ ] Status file (like OpenVPN's management interface)
- [ ] Integration tests with loopback TUN

**Deliverable:** production-quality personal VPN.

### Phase 5 — Extras (optional)

- [ ] Systemd service unit
- [ ] TAP (layer 2) mode
- [ ] TCP transport fallback
- [ ] SOCKS5 forward proxy integration
- [ ] Prometheus metrics

---

## Key Protocol Details

### Control Channel Opcodes

```python
P_CONTROL_HARD_RESET_CLIENT_V2 = 1  # Client initiates
P_CONTROL_HARD_RESET_SERVER_V2 = 2  # Server response
P_CONTROL_V1                     = 3  # Control packet (wrapped TLS data)
P_ACK_V1                         = 4  # Acknowledgement
P_DATA_V1                        = 5  # Encrypted data
P_DATA_V2                        = 6  # Encrypted data with packet ID
```

### Frame Header (2 bytes)

```
Bit:  0 1 2 3 4 5 6 7   8 ... 15
      +-+-+-+-+-------+-----------+
      |  Opcode | KeyID |  Payload |
      +-+-+-+-+-------+-----------+
```

`Opcode` (4 bits) | `KeyID` (4 bits, for key rotation) → followed by payload length and payload.

### Data Channel Encryption

```
Plaintext:  [IP Packet]
              │
              ▼ compress (optional)
              │
              ▼ AES-256-GCM Encrypt
              │
Wire format: [SessionID][PacketID][Nonce][Ciphertext][Auth Tag]
               4 bytes   4 bytes   12 bytes   var       16 bytes
```

### TLS Key Export

After TLS handshake, session keys are derived via:

```python
keying_material = ssl_context.session.export_keying_material(
    label=b"EXPORTER:PYVPN_DATA_KEY",
    length=64,
    context=b""
)
data_encrypt_key = keying_material[:32]   # AES-256 key
data_decrypt_key = keying_material[32:64] # AES-256 key (separate for bidirectional)
```

Alternatively, use X25519 ECDH for independent key exchange with HKDF derivation.

---

## Security Considerations

| Concern | Mitigation |
|---------|-----------|
| No PFS without ECDH | Use X25519 + HKDF for session keys |
| TLS version | Enforce TLS 1.3 minimum |
| Certificate validation | Full chain verification, hostname check |
| Auth tag truncation | Reject if AES-GCM tag validation fails |
| Replay attacks | PacketID counter + server-side dedup window |
| DoS on handshake | Limit concurrent handshakes per IP |
| Privilege separation | Drop root after TUN creation + cert load |
| Memory secrets | Use `ctypes` to `mlock()` key material |

---

## References

- [OpenVPN Protocol Specification](https://openvpn.net/community-resources/openvpn-protocol/)
- [OpenVPN Security Overview](https://openvpn.net/community-resources/security-overview/)
- [Linux TUN/TAP Documentation](https://www.kernel.org/doc/Documentation/networking/tuntap.txt)
- [RFC 8446 — TLS 1.3](https://datatracker.ietf.org/doc/html/rfc8446)
- [RFC 5116 — AEAD](https://datatracker.ietf.org/doc/html/rfc5116)
