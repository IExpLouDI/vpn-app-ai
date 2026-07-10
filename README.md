# Python VPN Application — Current State

## Overview

A minimal educational VPN prototype inspired by OpenVPN concepts. Creates a secure tunnel between a client and server, forwarding IP packets through an encrypted UDP/TCP connection.

> **Note:** This is an educational project. It is **not** intended for production use.

---

## Quick Start

### Prerequisites

- Linux with TUN support (`/dev/net/tun`)
- Python 3.10+
- `iproute2` (provides `ip` command)
- Root privileges (for TUN device and iptables)

### 1. Install

```bash
git clone https://github.com/IExpLouDI/vpn-app-ai.git
cd vpn-app-ai
pip install .
```

### 2. Generate certificates (optional)

Without certificates the handshake still works (no authentication). For production-like setup:

```bash
# CA
openssl req -x509 -newkey rsa:2048 -days 365 -nodes \
  -keyout ca.key -out ca.crt -subj "/CN=VPN-CA"

# Server
openssl req -newkey rsa:2048 -nodes \
  -keyout server.key -out server.csr -subj "/CN=server"
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -days 365

# Client
openssl req -newkey rsa:2048 -nodes \
  -keyout client.key -out client.csr -subj "/CN=client"
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out client.crt -days 365
```

### 3. Start the server

```bash
# With certificates (authenticated mode):
sudo pyvpn --server 10.8.0.0/24 --ca ca.crt --cert server.crt --key server.key

# Without certificates (dev mode):
sudo pyvpn --server 10.8.0.0/24
```

### 4. Connect a client

```bash
sudo pyvpn --remote SERVER_IP --ca ca.crt --cert client.crt --key client.key
```

Replace `SERVER_IP` with the server's actual IP address.

### 5. Using a config file (OpenVPN-style)

```bash
sudo pyvpn -c examples/server.conf
sudo pyvpn -c examples/client.conf
```

### Running without sudo (alternative)

If `sudo` doesn't preserve `PATH`, use a wrapper script:

```bash
cat > /usr/local/bin/pyvpn-sudo.sh << 'SCRIPT'
#!/bin/sh
PYTHONPATH=/path/to/vpn-app-ai/src exec /usr/bin/python3 -m app "$@"
SCRIPT
chmod +x /usr/local/bin/pyvpn-sudo.sh
sudo /usr/local/bin/pyvpn-sudo.sh --server 10.8.0.0/24
```

### Dev mode (no certificate authentication)

Omit `--ca`, `--cert`, and `--key` to skip certificate authentication. The
handshake and encryption still use X25519 + AES-256-GCM, but neither side
is verified. Useful for local testing.

---

## Implementation Status

| Component | Status | Files |
|---|---|---|
| TUN interface | ✅ Implemented | `src/tun.py` |
| UDP/TCP transport | ✅ Implemented | `src/client.py`, `src/server.py` |
| Custom ECDH handshake (X25519 + HKDF) | ✅ Implemented | `src/protocol/control.py`, `src/crypto/key_exchange.py` |
| Certificate loading & verification | ✅ Implemented | `src/crypto/certificates.py` |
| AES-256-GCM data encryption | ✅ Implemented | `src/crypto/cipher.py`, `src/protocol/data.py` |
| Packet fragmentation/reassembly | ✅ Implemented | `src/protocol/data.py` |
| LZ4 compression | ✅ Implemented | `src/protocol/data.py` |
| Config parser (OpenVPN-style) | ✅ Implemented | `src/config.py` |
| Multi-client server | ✅ Implemented | `src/server.py` |
| Virtual IP pool | ✅ Implemented | `src/routing.py` |
| NAT / iptables MASQUERADE | ✅ Implemented | `src/routing.py` |
| Keep-alive & timeout | ✅ Implemented | `src/client.py`, `src/server.py` |
| Auto-reconnect | ✅ Implemented | `src/client.py` |
| Windows TUN support | ⚠️ Partial | `src/tun_windows.py` |
| TLS 1.3 control channel | ❌ Planned (not implemented) | — |
| Replay protection (dedup window) | ❌ Planned (not implemented) | — |
| Privilege separation | ❌ Planned (not implemented) | — |
| Certificate generation scripts | ❌ Planned (not implemented) | — |
| Integration CI | ❌ Planned (not implemented) | — |

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────┐
│                    VPN Client                        │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │ TUN/TAP  │  │  Packet  │  │  Control Channel  │  │
│  │ Interface│◄─┤  Router  │◄─┤  (ECDH + Sign)   │  │
│  │  (dev)   │  │          │  │                   │  │
│  └────▲─────┘  └────▲─────┘  └────────▲──────────┘  │
│       │              │                 │             │
│  ┌────┴──────────────┴─────────────────┴──────────┐  │
│  │           Data Channel (AES-256-GCM)            │  │
│  │           UDP/TCP Transport                     │  │
│  └───────────────────▲────────────────────────────┘  │
│                      │ encrypted packets             │
├──────────────────────┼──────────────────────────────┤
│                 Internet                             │
├──────────────────────┼──────────────────────────────┤
│                      ▼                              │
│  ┌───────────────────┴────────────────────────────┐  │
│  │           Data Channel (AES-256-GCM)            │  │
│  │           UDP/TCP Transport                     │  │
│  └───────────────────▲────────────────────────────┘  │
│       │              │                 │             │
│  ┌────▼──────────────┴─────────────────▼──────────┐  │
│  │ TUN/TAP  │  Packet  │  Control Channel  │  Auth  │  │
│  │ Interface│  Router  │  (ECDH + Sign)     │  PEM   │  │
│  └──────────┘  └──────────┘  └───────────────────┘  │
│                    VPN Server                        │
└─────────────────────────────────────────────────────┘
```

### Two-Channel Design (OpenVPN-inspired)

| Channel | Purpose | Protocol | Encryption |
|---|---|---|---|
| Control Channel | Handshake, auth, key exchange | Custom ECDH (X25519) + certificate signing | X.509 certificates |
| Data Channel | IP packet tunneling | AES-256-GCM | Symmetric session keys (HKDF-derived) |

Both channels are multiplexed over a single UDP connection using a lightweight frame header.

---

## Core Components

### 1. TUN Interface Manager — `tun.py`

Creates and manages the virtual TUN network interface.

- Opens `/dev/net/tun` via `open()` + `fcntl.ioctl(TUNSETIFF)`
- Reads raw IP packets from the interface
- Writes decrypted IP packets into the interface
- Configures IP address and MTU via subprocess calls to `ip`
- Handles interface lifecycle (create, configure, destroy)

### 2. Control Channel — `protocol/control.py`

Manages the handshake, authentication, and key exchange.

**Handshake sequence:**

1. Client sends `HARD_RESET_CLIENT`
2. Server responds `HARD_RESET_SERVER`
3. Client sends `CLIENT_HELLO` (certificate + ephemeral X25519 public key)
4. Server verifies client cert, derives shared key via X25519 + HKDF, responds with `SERVER_HELLO` (cert + pubkey + signature)
5. Client verifies server cert + signature, derives shared key, sends `CLIENT_FINISHED` (signature)
6. Server verifies client signature → session established
7. Periodic `KEEPALIVE` to maintain session

**Packet format:**
```
[Opcode (1)] [SessionID (8)] [Payload]
```

### 3. Data Channel — `protocol/data.py`

Encrypts and tunnels IP packets.

- Reads raw IP packet from TUN interface
- Compresses payload (optional, LZ4)
- Encrypts with AES-256-GCM using session key
- Wraps in data frame header
- Sends over UDP/TCP to peer
- Peer decrypts → decompresses → writes to its TUN interface

**Data frame format:**
```
[PacketID (4)] [Nonce (12)] [Ciphertext...] [Tag (16)]
```

### 4. Crypto Module — `crypto/`

| File | Responsibility |
|---|---|
| `cipher.py` | AES-256-GCM encrypt/decrypt, key import |
| `certificates.py` | Load/verify X.509 PEM certificates |
| `key_exchange.py` | X25519 ECDH for PFS, key derivation (HKDF) |

### 5. Configuration — `config.py`

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

### 6. Routing — `routing.py`

Manages system routing and NAT rules.

- Adds route to VPN subnet via TUN interface
- Pushes client-specific routes from server
- Manages `iptables` MASQUERADE rule for NAT
- Optionally redirects all traffic (default gateway) through VPN

### 7. Server — `server.py`

Multi-client VPN server using `asyncio`.

- Accepts incoming UDP/TCP connections
- Manages client sessions (handshake → data → disconnect)
- Virtual IP allocation pool (`ifconfig-pool`)
- Routes traffic between clients and LAN
- Connection timeout and cleanup

### 8. Client — `client.py`

VPN client.

- Resolves server hostname
- Initiates control channel handshake
- Configures local TUN interface with assigned IP
- Reads/writes encrypted packets bidirectionally
- Automatic reconnection on timeout

---

## Technology Stack

| Component | Library | Rationale |
|---|---|---|
| TUN/TAP | `fcntl` (stdlib) | Direct kernel interface, minimal |
| X.509 certs | `cryptography` | Load/verify PEM certificates |
| AES-256-GCM | `cryptography` | Authenticated encryption |
| X25519/ECDH | `cryptography` | Key exchange for PFS |
| Async I/O | `asyncio` (stdlib) | Single-threaded concurrency |
| Config parser | `configparser` | INI-like format |
| Compression | `lz4` | Fast, optional data compression |
| CLI | `argparse` (stdlib) | Command-line arguments |

---

## Project Structure

```
vpn-app/
├── README.md
├── requirements.txt
├── setup.py
├── examples/
│   ├── server.conf
│   └── client.conf
├── src/
│   ├── __init__.py
│   ├── app.py                      # Entry point
│   ├── cli.py                      # CLI argument parsing
│   ├── config.py                   # Config file parser
│   ├── tun.py                      # TUN interface (Linux)
│   ├── tun_windows.py              # TUN interface (Windows, partial)
│   ├── server.py                   # VPN server
│   ├── client.py                   # VPN client
│   ├── routing.py                  # Routing & iptables
│   ├── status.py                   # Status file output
│   ├── crypto/
│   │   ├── __init__.py
│   │   ├── cipher.py               # AES-256-GCM
│   │   ├── certificates.py         # Load/verify certs
│   │   └── key_exchange.py         # X25519 + HKDF
│   ├── protocol/
│   │   ├── __init__.py
│   │   ├── control.py              # Control channel (ECDH handshake)
│   │   ├── data.py                 # Data channel (encrypted tunnel)
│   │   ├── packet.py               # Binary packet format
│   │   ├── framing.py              # TCP frame length prefixing
│   │   └── messages.py             # Opcodes and message types
│   └── auth/
│       └── __init__.py
└── tests/
    ├── __init__.py
    ├── test_handshake.py
    ├── test_integration.py
    ├── test_multi_client.py
    └── test_phase4.py
```

---

## Handshake Protocol Details

### Opcodes

| Value | Name | Direction |
|---|---|---|
| 1 | HARD_RESET_CLIENT | Client → Server |
| 2 | HARD_RESET_SERVER | Server → Client |
| 3 | CONTROL | Bidirectional |
| 4 | ACK | Bidirectional |
| 5 | DATA | Bidirectional |

### Control Message Types

| Value | Name | Description |
|---|---|---|
| 1 | CLIENT_HELLO | Client cert + ephemeral public key |
| 2 | SERVER_HELLO | Server cert + ephemeral public key + signature |
| 3 | CLIENT_FINISHED | Client signature to complete handshake |
| 4 | KEEPALIVE | Session keep-alive |
| 5 | SHUTDOWN | Session termination |
| 6 | IP_ASSIGN | Server assigns virtual IP to client |

### Key Exchange

After the handshake, session keys are derived via X25519 ECDH + HKDF:

```python
shared = private_key.exchange(peer_public_key)
hkdf = HKDF(
    algorithm=hashes.SHA256(),
    length=32,
    salt=session_id + peer_session_id,
    info=b"pyvpn-data-channel",
)
session_key = hkdf.derive(shared)
```

### Data Channel Encryption

```
Plaintext:  [IP Packet]
              │
              ▼ compress (optional, LZ4)
              │
              ▼ AES-256-GCM Encrypt
              │
Wire format: [PacketID][Nonce][Ciphertext][Auth Tag]
               4 bytes  12 bytes   var       16 bytes
```

---

## Planned Enhancements

- **TLS 1.3 control channel**: Replace custom handshake with full TLS 1.3 over UDP
- **Replay protection**: PacketID counter + server-side dedup window
- **Privilege separation**: Drop root after TUN creation + cert load
- **Certificate generation scripts**: `certs/generate.sh` using openssl
- **Integration CI**: Automated test runs via GitHub Actions
- **Windows support**: Full TUN driver integration

---

## Security Considerations

| Concern | Current Status |
|---|---|
| Forward secrecy (PFS) | ✅ X25519 ECDH + ephemeral keys |
| Data encryption | ✅ AES-256-GCM |
| Certificate validation | ✅ Chain verification, signature checks |
| Auth tag verification | ✅ AES-GCM tag validation |
| Key derivation | ✅ HKDF with salt |
| TLS 1.3 control channel | ❌ Planned — currently custom handshake |
| Replay attack mitigation | ❌ Planned — counter exists, no dedup window yet |
| DoS protection on handshake | ❌ Planned |
| Privilege separation | ❌ Planned |
| Memory secret locking | ❌ Planned |

---

## Requirements

- Linux (TUN support)
- Python 3.10+
- Root privileges (for TUN device and iptables)
- Dependencies: `cryptography`, `lz4` (optional)

---

## References

- [OpenVPN Protocol Specification](https://openvpn.net/community-resources/openvpn-protocol/)
- [Linux TUN/TAP Documentation](https://www.kernel.org/doc/Documentation/networking/tuntap.txt)
- [RFC 5116 — AEAD](https://datatracker.ietf.org/doc/html/rfc5116)
