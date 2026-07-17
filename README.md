# Python VPN Application

## Overview

A minimal educational VPN prototype inspired by OpenVPN concepts. It creates a secure
tunnel between a client and a server, forwarding IP packets through an encrypted
UDP/TCP connection.

> **Disclaimer:** This is an educational project. It is **not** intended for production
> or commercial use and has **not** undergone a cryptographic audit. Large parts of the
> code and documentation were AI-generated ("vibe-coded" / neuro-slop) and may contain
> bugs, inconsistencies, or unreviewed security flaws — do not rely on it to protect
> real traffic. See [Threat Model and Non-Goals](#threat-model-and-non-goals).

---

## Implementation Status (canonical)

This is the **single source of truth** for feature status. All other sections and the
companion doc [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md) reference
this table. Status legend:

- ✅ **Implemented** — available in the running VPN today
- ⚠️ **Partial** — works with caveats / opt-in only
- 🧪 **Experimental** — implemented as a module but not the default runtime path
- ❌ **Planned** — not implemented

| Feature | Status | Default | Notes / Files |
|---|---|---|---|
| TUN interface (Linux) | ✅ Implemented | on (required) | `src/tun.py`; needs `/dev/net/tun` + `CAP_NET_ADMIN`/root |
| TUN interface (Windows) | ⚠️ Partial | off | `src/tun_windows.py`; TUN only, no iptables/routing |
| UDP / TCP transport | ✅ Implemented | UDP | `proto udp\|tcp`; `src/client.py`, `src/server.py` |
| Custom ECDH handshake (X25519 + HKDF) | ✅ Implemented | **on (default control)** | `src/protocol/control.py`, `src/crypto/key_exchange.py` |
| Certificate loading & verification | ✅ Implemented | optional | omitted → dev mode (no auth); `src/crypto/certificates.py` |
| AES-256-GCM data encryption | ✅ Implemented | on | `src/crypto/cipher.py`, `src/protocol/data.py` |
| Packet fragmentation / reassembly | ✅ Implemented | automatic | auto for payloads > 1400 B; MTU 1500; `src/protocol/data.py` |
| LZ4 compression | ✅ Implemented | **off** (opt-in `--comp-lzo`) | `src/protocol/data.py` |
| Config parser (OpenVPN-style) | ✅ Implemented | — | `src/config.py` |
| Multi-client server | ✅ Implemented | on (server mode) | `src/server.py` |
| Virtual IP pool | ✅ Implemented | on (server mode) | `src/routing.py` |
| NAT / iptables MASQUERADE | ✅ Implemented | on (server mode) | auto-detects default-route interface; rule removed on shutdown; requires root/`iptables` |
| Keep-alive & timeout | ✅ Implemented | on | `keepalive 10 120` |
| Auto-reconnect | ✅ Implemented | on (client) | `src/client.py` |
| Replay protection (dedup window) | ✅ Implemented | on | sliding-window PacketID dedup; `src/protocol/replay.py` |
| TLS 1.3 control channel | 🧪 Experimental | **off** | mutual TLS 1.3 over TCP in `src/protocol/tls_channel.py`; **not** wired as the default control path (the running VPN still uses the custom X25519 ECDH handshake) |
| Privilege separation | ⚠️ Partial | **off** (opt-in `--user`) | drops root after setup; per-client routes / NAT still require root; `src/privileges.py` |
| Certificate generation scripts | ❌ Planned | — | `certs/generate.sh` |
| Integration CI (privileged) | ❌ Planned | — | root + TUN system tests in GitHub Actions |
| Windows full support | ❌ Planned | — | full TUN driver + routing integration |
| DoS protection on handshake | ❌ Planned | — | rate limiting |
| Key rotation / renegotiation | ❌ Planned | — | no rekeying |
| Memory secret locking (`mlock`) | ❌ Planned | — | key material can hit swap |

---

## Current Capabilities

What is available in the **runtime today** (no flags required unless noted):

- Point-to-multipoint VPN: one server, many clients, each with a virtual IP from a pool.
- Encrypted data plane: AES-256-GCM over UDP (default) or TCP.
- Authenticated control plane via X25519 ECDH + HKDF key derivation and X.509
  certificate verification (server and client certs, CA-chained).
- Replay protection on the data channel (sliding-window PacketID dedup).
- IP packet fragmentation/reassembly and optional LZ4 compression.
- Keep-alive, session timeout, and client auto-reconnect.
- NAT (iptables MASQUERADE) on the server: set up automatically on the default-route
  interface at startup and removed on shutdown.
- **Dev mode**: omit `ca`/`cert`/`key` to run the handshake without certificate
  authentication (encryption still active, but neither side is verified).

## Experimental Features

- **TLS 1.3 control channel** — `src/protocol/tls_channel.py` provides a mutual-TLS-1.3
  TCP control channel with a tested API (`tests/test_tls_channel.py`). It is **not** yet
  wired into the default server/client runtime, which still uses the custom ECDH
  handshake. Treat it as a reference module / building block, not a production path.

## Planned Work

All remaining work — priorities, affected code, suggested approaches — lives in
**[`docs/BACKLOG.md`](docs/BACKLOG.md)** (single source of truth for what to do
next). Headline items: handshake DoS protection, certificate expiry validation,
key rotation, privileged integration CI, full Windows support.

---

## Quick Start

> For a complete two-machine walkthrough (certificates, settings reference,
> troubleshooting) see [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

### Prerequisites

- Linux with TUN support (`/dev/net/tun`)
- Python 3.10+
- `iproute2` (provides the `ip` command)
- Root privileges (for the TUN device and `iptables`)

### 1. Install

```bash
git clone https://github.com/IExpLouDI/vpn-app-ai.git
cd vpn-app-ai
pip install .
```

### 2. Generate certificates (optional)

Without certificates the handshake still works (dev mode, no authentication). For
authenticated mode:

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
# Authenticated mode:
sudo pyvpn --server 10.8.0.0/24 --ca ca.crt --cert server.crt --key server.key

# Dev mode (no certificates):
sudo pyvpn --server 10.8.0.0/24
```

### 4. Connect a client

```bash
sudo pyvpn --remote SERVER_IP --ca ca.crt --cert client.crt --key client.key
```

Replace `SERVER_IP` with the server's actual IP address.

### Running without sudo (alternative)

If `sudo` does not preserve `PATH`, use a wrapper that points at the `src` package:

```bash
cat > /usr/local/bin/pyvpn-sudo.sh << 'SCRIPT'
#!/bin/sh
PYTHONPATH=/path/to/vpn-app-ai/src exec /usr/bin/python3 -m app "$@"
SCRIPT
chmod +x /usr/local/bin/pyvpn-sudo.sh
sudo /usr/local/bin/pyvpn-sudo.sh --server 10.8.0.0/24
```

### Dev mode (no certificate authentication)

Omit `--ca`, `--cert`, and `--key` to skip certificate authentication. The handshake and
encryption still use X25519 + AES-256-GCM, but neither side is verified. Useful for
local testing only.

---

## Minimal Working Setup

A single client/server pair that can be launched and verified end-to-end. The two config
files are intentionally symmetric — `examples/server.conf` and `examples/client.conf`.

**`examples/server.conf`**

```ini
dev tun
proto udp
port 1194
server 10.8.0.0 255.255.255.0
ifconfig-pool 10.8.0.2 10.8.0.100
ca ca.crt
cert server.crt
key server.key
cipher AES-256-GCM
keepalive 10 120
verb 3
```

**`examples/client.conf`**

```ini
dev tun
proto udp
remote 203.0.113.10
port 1194
ca ca.crt
cert client.crt
key client.key
cipher AES-256-GCM
keepalive 10 120
verb 3
```

**Launch**

```bash
# Terminal 1 (server, as root):
sudo pyvpn -c examples/server.conf

# Terminal 2 (client, as root):
sudo pyvpn -c examples/client.conf
```

**Certificate requirements**

- A shared CA (`ca.crt`) must be present on both sides.
- `server.crt`/`server.key` are loaded by the server; `client.crt`/`client.key` by the
  client. Certs must chain to `ca.crt` (see *Quick Start* for an `openssl` recipe).

**Expected verification result**

- Client log shows `Data channel ready` and `TUN configured: 10.8.0.x/24`.
- The client receives a virtual IP from the server pool (e.g. `10.8.0.2`).
- Traffic routed to the tunnel (or, with `--redirect-gateway`, all traffic) is encrypted
  with AES-256-GCM and protected against replay.
- Stopping either side closes the transport; the peer detects the loss via keepalive
  timeout, tears the session down, and the client auto-reconnects.

---

## Configuration Reference

The config file is an **OpenVPN-style contract**: every directive maps to a typed
`Config` field (`src/config.py`). Unknown directives are preserved under
`extra_options` and ignored by the core. **Only explicitly provided** CLI flags
override file values; parser defaults never stomp the file. `proto`, `port`, and
`verb` are validated in `Config.__post_init__` (out-of-range values raise
`ValueError`).

| Directive | Purpose | Type | Required | Allowed values | Default | Constraints |
|---|---|---|---|---|---|---|
| `dev` | TUN device name | string | no | any | `tun` | Linux only; Windows partial |
| `proto` | Transport protocol | enum | no | `udp`, `tcp` | `udp` | — |
| `port` | Listen/connect port | int | no | 1–65535 | `1194` | — |
| `remote` | Server address (client) | string | client mode | hostname/IP | — | required in client mode |
| `server` | Server subnet (server) | CIDR | server mode | `A.B.C.D/M` (or `A.B.C.D netmask`) | — | required in server mode |
| `ifconfig` | Client static IP/CIDR | CIDR | no | `A.B.C.D/M` | — | client side |
| `ifconfig-pool` | Client IP range (server) | range | no | `start-end` | subnet−.2 … −.254 | server side |
| `ca` | CA certificate (PEM) | path | auth mode | file | — | enables cert verification |
| `cert` | Local certificate (PEM) | path | auth mode | file | — | requires `ca`+`key` |
| `key` | Local private key (PEM) | path | auth mode | file | — | requires `ca`+`cert` |
| `cipher` | Data-channel cipher | string | no | `AES-256-GCM` | `AES-256-GCM` | only AES-256-GCM implemented |
| `comp-lzo` | Enable LZ4 compression | flag | no | (present/absent) | off | opt-in |
| `keepalive` | Keepalive interval/timeout | pair | no | `int int` | `10 120` | seconds |
| `verb` | Log verbosity | int | no | 0–4 | `1` | — |
| `redirect-gateway` | Route all traffic via VPN | flag | no | (present/absent) | off | client-side: client installs a default route via the tunnel itself |
| `status` | Periodic status file | path | no | file | — | — |
| `user` | Drop privileges after setup | string | no | system username | — | privilege separation (partial) |

> **Auth mode:** if `ca`/`cert`/`key` are all omitted, the process runs in **dev mode**
> (handshake succeeds without certificate verification). Providing them enables mutual
> X.509 authentication.

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

Both channels are multiplexed over a single UDP/TCP connection using a lightweight frame
header.

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

Parses OpenVPN-style configuration files (see [Configuration Reference](#configuration-reference)).
Returns a `Config` dataclass with typed fields.

### 6. Routing — `routing.py`

Manages system routing and NAT rules.

- Adds route to VPN subnet via TUN interface
- Assigns virtual IPs to clients (`IP_ASSIGN` control message)
- Manages the `iptables` MASQUERADE rule for NAT (auto-detected default interface,
  removed on shutdown)
- Client-side `redirect-gateway`: optionally routes all traffic (default gateway)
  through the tunnel

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
| Config parser | custom (hand-rolled) | OpenVPN-style whitespace directives |
| Compression | `lz4` | Fast, optional data compression |
| CLI | `argparse` (stdlib) | Command-line arguments |

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
| 4 | KEEPALIVE | Session keep-alive (sent by server, echoed by client) |
| 5 | SHUTDOWN | Defined but **not currently used** — teardown is implicit (transport close + keepalive timeout) |
| 6 | IP_ASSIGN | Server assigns virtual IP to client |

### Key Exchange

After the handshake, session keys are derived via X25519 ECDH + HKDF. The salt is the
order-independent concatenation of both session IDs, so client and server compute the
same value regardless of their roles:

```python
a, b = session_id, peer_session_id
salt = a + b if a < b else b + a  # same on both sides
hkdf = HKDF(
    algorithm=hashes.SHA256(),
    length=32,
    salt=salt,
    info=b"pyvpn-data-channel",
)
session_key = hkdf.derive(private_key.exchange(peer_public_key))
```

### Data Channel Encryption

```
Plaintext:  [CompByte][IP Packet]
             1 byte: 0 = none, 1 = LZ4 (already compressed, if smaller)
             │  (for fragmented packets: [0x80|0][Total][Index][chunk])
             ▼ AES-256-GCM Encrypt (AAD = SharedSessionID + PacketID)
             │
Wire format: [PacketID][Nonce][Ciphertext][Auth Tag]
             4 bytes  12 bytes   var       16 bytes
```

The session ID on the wire for DATA packets is `SharedSessionID = client_id XOR
server_id` (8 bytes).

---

## Platform Support Matrix

| Platform | TUN | Routing / NAT | Privilege drop | Status |
|---|---|---|---|---|
| Linux | ✅ Full (`/dev/net/tun`) | ✅ `ip` + `iptables` | ✅ (`--user`, partial) | Primary / supported |
| Windows | ⚠️ Partial (`tun_windows.py`) | ❌ Not implemented | ❌ Not implemented | Experimental, TUN only |
| macOS / BSD | ❌ Not implemented | ❌ Not implemented | ❌ Not implemented | Unsupported |

## Runtime Profile Matrix

| Profile | Supported | Notes |
|---|---|---|
| UDP + custom ECDH control + cert verify | ✅ Default | the standard, supported runtime |
| TCP + custom ECDH control + cert verify | ✅ Supported | set `proto tcp` |
| Dev mode (no certificates) | ✅ Supported | no peer authentication |
| Compression (`--comp-lzo`) | ✅ Supported | opt-in; sender-side flag, packets self-describe (per-packet comp byte), receiver only needs `lz4` installed |
| Fragmentation | ✅ Automatic | triggered for > 1400 B payloads |
| Multi-client | ✅ Supported | server mode with IP pool |
| TLS 1.3 control channel | 🧪 Experimental | module only; not the default control path |
| Privilege separation | ⚠️ Partial | opt-in `--user`; per-client routes/NAT still need root |

---

## Threat Model and Non-Goals

This section is the formal security frame. It intentionally lists what is **not**
covered, because the project is educational.

**Covered (implemented & tested — see [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md)):**

- Passive eavesdropping → AES-256-GCM encryption.
- Man-in-the-middle → X.509 certificate verification + handshake signatures.
- Forward secrecy → ephemeral X25519 ECDH keys.
- Replay attacks → sliding-window PacketID dedup on the data channel.
- Key/material leakage in transit → authenticated encryption (GCM tag).

**Not covered (Planned / Non-Goals):**

- **No full hardening.** The process runs with root for most of its life; privilege
  separation (`--user`) is partial — per-client route installation and NAT still require
  root, so a compromised process retains significant privileges.
- **Replay mitigation is data-channel only.** The control handshake has no replay/DoS
  protection; an attacker can trigger repeated handshakes.
- **No key rotation.** A session key is fixed for the session lifetime; there is no
  renegotiation.
- **Dev mode is insecure by design.** Omitting certificates removes all authentication.
- **Windows support is incomplete** (TUN only, no routing/NAT/privilege drop).
- **CI/integration validation is incomplete.** Unit and integration tests run without
  root; privileged system tests are not yet automated.
- **Memory secrets are not locked** (`mlock` not used) — key material may reach swap.

**Non-Goals:** production deployment, audited cryptographic design, compliance
certifications, and support for untrusted/multi-tenant environments.

---

## Project Structure

```
vpn-app-ai/
├── README.md
├── requirements.txt
├── setup.py
├── pyproject.toml                  # pytest + ruff config
├── docs/
│   ├── ARCHITECTURE_AS_IS.md       # Authoritative as-built description
│   ├── BACKLOG.md                  # Remaining work (single source of truth)
│   ├── DEPLOYMENT.md               # Two-machine setup guide
│   ├── IMPLEMENTATION_STATUS.md    # Capability matrix
│   ├── SECURITY_MODEL.md           # Security claims + evidence
│   ├── SKILLS.md                   # Required knowledge map
│   └── TEST_STRATEGY.md            # Test layers & CI expectations
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
│   ├── routing.py                  # Routing, NAT & iptables
│   ├── status.py                   # Status file output (client)
│   ├── privileges.py               # Opt-in privilege drop
│   ├── crypto/
│   │   ├── cipher.py               # AES-256-GCM
│   │   ├── certificates.py         # Load/verify certs
│   │   └── key_exchange.py         # X25519 + HKDF
│   ├── protocol/
│   │   ├── control.py              # Control channel (ECDH handshake)
│   │   ├── data.py                 # Data channel (encrypted tunnel)
│   │   ├── replay.py               # Replay protection (dedup window)
│   │   ├── tls_channel.py          # Experimental TLS 1.3 control channel
│   │   ├── packet.py               # Binary packet format
│   │   ├── framing.py              # TCP frame length prefixing
│   │   └── messages.py             # Opcodes and message types
│   └── auth/
│       └── __init__.py
└── tests/
    ├── test_handshake.py           # Auth + dev-mode handshake flows
    ├── test_crypto.py
    ├── test_config.py
    ├── test_cli.py                 # CLI/file override semantics
    ├── test_data.py
    ├── test_replay.py
    ├── test_tls_channel.py
    ├── test_privileges.py
    ├── test_routing.py
    ├── test_status.py
    └── legacy/                     # Privileged system tests (root + TUN)
```

---

## Requirements

- Linux (TUN support)
- Python 3.10+
- Root privileges (for TUN device and iptables)
- Dependencies: `cryptography` (required), `lz4` (declared in packaging, but optional
  at runtime — compression auto-disables with a warning if `lz4` is missing)

---

## References

- [OpenVPN Protocol Specification](https://openvpn.net/community-resources/openvpn-protocol/)
- [Linux TUN/TAP Documentation](https://www.kernel.org/doc/Documentation/networking/tuntap.txt)
- [RFC 5116 — AEAD](https://datatracker.ietf.org/doc/html/rfc5116)
