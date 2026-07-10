# Required Hard Skills

Before working on this project, ensure you have the following skills and knowledge. Each section links to relevant source files and concepts in the codebase.

---

## 1. Python — Core Language

### Proficiency Level: Advanced

| Skill | Where it's used | Key files |
|---|---|---|
| Async I/O (`asyncio`) | UDP/TCP event loop, concurrent clients | `src/client.py`, `src/server.py` |
| Binary protocol handling (`struct`) | Packet encoding/decoding, framing | `src/protocol/packet.py`, `src/protocol/framing.py` |
| Datagram transport (`asyncio.DatagramProtocol`) | UDP client/server | `src/client.py:285`, `src/server.py:330` |
| Stream I/O (`asyncio.StreamReader/Writer`) | TCP transport | `src/client.py:174`, `src/server.py:254` |
| Signal handling | Graceful shutdown | `src/client.py:110`, `src/server.py:115` |
| Subprocess management | `ip`, `iptables` calls | `src/tun.py`, `src/routing.py` |
| Context managers (`__enter__`/`__exit__`) | TUN lifecycle | `src/tun.py:90` |
| Dataclasses | Config model | `src/config.py` |
| Enums + IntEnum | Opcodes, states | `src/protocol/messages.py`, `src/protocol/control.py:24` |
| `argparse` | CLI argument parsing | `src/cli.py` |
| `logging` | Structured logging | All modules |
| Type hints (`str \| None`, generics) | Full codebase | All modules |

### Must understand:
- How `asyncio` event loop works (especially `add_reader` for fd monitoring)
- Difference between `DatagramProtocol` and `StreamReader/Writer`
- Binary data packing with `struct.pack`/`unpack` (endianness, format strings)
- Python's `import` system and `package_dir` in `setup.py`

---

## 2. Cryptography

### Proficiency Level: Intermediate

| Skill | Where it's used | Key files |
|---|---|---|
| AES-256-GCM (authenticated encryption) | Data channel encryption | `src/crypto/cipher.py` |
| X25519 ECDH (Elliptic Curve Diffie-Hellman) | Key exchange, forward secrecy | `src/crypto/key_exchange.py` |
| HKDF (HMAC-based Key Derivation Function) | Session key derivation | `src/crypto/key_exchange.py:27` |
| X.509 certificates (PEM) | Mutual authentication | `src/crypto/certificates.py` |
| RSA/EC signature creation and verification | Handshake signing | `src/protocol/control.py:71` |
| Nonce management | Replay prevention basis | `src/crypto/cipher.py:17` |

### Must understand:
- Difference between symmetric (AES) and asymmetric (ECDH) cryptography
- What AES-GCM provides: confidentiality + integrity + authentication
- Why nonces must never repeat with the same key
- How ECDH provides forward secrecy (PFS)
- Certificate chain validation (CA → intermediate → leaf)
- PKCS1v15 vs ECDSA signature schemes

### Cryptographic operations flow in this project:

```
Client                              Server
  │                                    │
  │──── HARD_RESET_CLIENT ────────────→│
  │←─── HARD_RESET_SERVER ─────────────│
  │                                    │
  │──── CLIENT_HELLO ─────────────────→│  (cert + X25519 pubkey)
  │    │                                │  Server verifies cert against CA
  │    │                                │  Server derives shared key via ECDH+HKDF
  │←─── SERVER_HELLO ──────────────────│  (cert + X25519 pubkey + signature)
  │    │                                │  
  │    Client verifies server cert      │
  │    Client verifies server signature │
  │    Client derives shared key        │
  │──── CLIENT_FINISHED ──────────────→│  (signature)
  │    │                                │  Server verifies client signature
  │    │                                │  Session ESTABLISHED
  │──── DATA (AES-256-GCM) ───────────→│  Encrypted IP packets
```

---

## 3. Network Engineering

### Proficiency Level: Intermediate

| Skill | Where it's used | Key files |
|---|---|---|
| VPN concepts (OpenVPN, WireGuard) | Overall architecture | `README.md`, `docs/ARCHITECTURE_AS_IS.md` |
| TUN/TAP interfaces | Virtual tunnel device | `src/tun.py`, `src/tun_windows.py` |
| IP addressing and CIDR | Subnet configuration, IP pool | `src/config.py:59`, `src/routing.py` |
| UDP and TCP transport | Data plane | `src/client.py`, `src/server.py` |
| IP packet structure (IPv4 header) | Packet routing, destination lookup | `src/server.py:344` |
| MTU and fragmentation | Packet size management | `src/protocol/data.py:15` |
| Network namespaces | Integration testing | `tests/legacy/` |

### Must understand:
- How a TUN interface differs from TAP (L3 vs L2)
- CIDR notation: `10.8.0.0/24` → network, broadcast, usable range
- The OSI model layers relevant to VPNs (L3 IP, L4 UDP/TCP)
- How `iptables MASQUERADE` provides NAT
- Difference between `ip route add` and `ip addr add`
- How `/dev/net/tun` and `ioctl(TUNSETIFF)` work on Linux

---

## 4. Linux System Administration

### Proficiency Level: Intermediate

| Skill | Where it's used | Key files |
|---|---|---|
| TUN device management | Interface lifecycle | `src/tun.py` |
| `ip` commands (`addr`, `route`, `link`) | Network configuration | `src/tun.py`, `src/routing.py` |
| `iptables` | NAT/masquerade | `src/routing.py:66` |
| IP forwarding (`/proc/sys/net/ipv4/ip_forward`) | Routing between interfaces | `src/routing.py:81` |
| Root privileges | All TUN/iptables operations | `src/tun.py`, `src/routing.py` |
| File descriptors and `fcntl` | TUN device I/O | `src/tun.py` |

### Must understand:
- Why TUN operations require `CAP_NET_ADMIN` or root
- How to check and enable IP forwarding
- The difference between `ip addr add` and `ifconfig`
- How `iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE` works
- How file descriptors work with `asyncio.add_reader`

---

## 5. Testing

### Proficiency Level: Intermediate

| Skill | Where it's used | Key files |
|---|---|---|
| pytest | Test framework | `tests/` |
| Fixtures (`conftest.py`, `tmp_path`) | Test setup, cert generation | `tests/conftest.py` |
| Certificate generation for tests | Mock PKI | `tests/conftest.py` |
| `pytest.raises` | Exception testing | `tests/test_crypto.py` |
| Parametrized tests | Multiple scenarios | (to be added) |
| Integration testing with subprocesses | Client-server tests | `tests/legacy/` |

### Testing layers:

```
┌─────────────────────────────────────────────┐
│ Layer 3: System tests (root + TUN)          │
│ tests/legacy/                               │
│ Run manually: sudo pytest tests/legacy/      │
├─────────────────────────────────────────────┤
│ Layer 2: Integration tests (no root)        │
│ test_handshake.py (full protocol handshake)  │
├─────────────────────────────────────────────┤
│ Layer 1: Unit tests (no root, fast)         │
│ test_config.py, test_crypto.py,             │
│ test_protocol.py, test_data.py,             │
│ test_routing.py, test_status.py             │
└─────────────────────────────────────────────┘
```

---

## 6. CI/CD

### Proficiency Level: Basic

| Skill | Where it's used | Key file |
|---|---|---|
| GitHub Actions | Automated testing | `.github/workflows/python-ci.yml` |
| Ruff (linter) | Code quality | `pyproject.toml` (ruff config) |
| Pip packaging | Distribution | `setup.py` |

### CI pipeline steps:
1. `pip install -r requirements.txt` — install deps (cryptography, lz4)
2. `pip install pytest ruff` — install dev tools
3. `ruff check .` — static analysis (import sorting, unused imports, etc.)
4. `pytest -v --tb=short` — run unit + integration tests
5. `pip install .` — verify package builds and installs

---

## 7. Security Engineering

### Proficiency Level: Intermediate

| Skill | Where it's used | Key files |
|---|---|---|
| Threat modeling | Understanding attack surface | `docs/SECURITY_MODEL` |
| Replay attack prevention | Packet deduplication | `src/protocol/data.py` (planned) |
| Forward secrecy (PFS) | ECDH ephemeral keys | `src/crypto/key_exchange.py` |
| Certificate validation | Mutual authentication | `src/crypto/certificates.py:21` |
| Privilege separation | Dropping root after setup | Planned |
| Memory security (mlock) | Preventing key leakage | Planned |

### Threat model summary:

| Threat | Mitigation | Status |
|---|---|---|
| Passive eavesdropping | AES-256-GCM encryption | ✅ Implemented |
| Man-in-the-middle | Certificate verification + signatures | ✅ Implemented |
| Forward secrecy compromise | X25519 ephemeral keys | ✅ Implemented |
| Replay attacks | Packet counter + dedup window | ❌ Planned |
| DoS on handshake | Rate limiting | ❌ Planned |
| Key material in swap | mlock() | ❌ Planned |

---

## 8. Protocol Design

### Proficiency Level: Intermediate

| Skill | Where it's used | Key files |
|---|---|---|
| Binary protocol design | Wire format specification | `src/protocol/` |
| State machines | Handshake state transitions | `src/protocol/control.py:24` |
| Protocol multiplexing | Control + data over single UDP | `src/protocol/packet.py` |
| Keep-alive mechanism | Session maintenance | `src/client.py:141`, `src/server.py:166` |

### Wire format overview:

```
Packet header (9 bytes):
┌─────────┬──────────────┐
│ Opcode  │  SessionID   │
│ (1 byte)│  (8 bytes)   │
└─────────┴──────────────┘

Control message (after header):
┌──────────┬────────────────┐
│ MsgType  │    Payload     │
│ (1 byte) │   (variable)   │
└──────────┴────────────────┘

Data message (after header):
┌──────────┬──────────┬──────────┬────────────┬────────┐
│ PacketID │  Nonce   │ Cipher   │ Auth Tag   │ ...    │
│ (4 bytes)│(12 bytes)│ (var)    │ (16 bytes) │        │
└──────────┴──────────┴──────────┴────────────┘

TCP framing (prefixes every packet):
┌────────────┬──────────────┐
│  Length    │  Packet data │
│ (2 bytes)  │  (variable)  │
└────────────┴──────────────┘
```

---

## 9. Development Tools

| Tool | Purpose |
|---|---|
| Git + GitHub | Version control, PRs, CI |
| Python 3.10+ | Runtime |
| `cryptography` | All crypto operations |
| `lz4` | Optional compression |
| Ruff | Linter + import sorter |
| pytest | Test framework |
| Wireshark / tcpdump | Debugging encrypted tunnel |

---

## Recommended Learning Path

If you're missing some skills, study in this order:

1. **Python asyncio** — read the official docs, practice echo client/server
2. **Binary protocols with struct** — practice pack/unpack with different formats
3. **AES-GCM with cryptography library** — encrypt/decrypt sample data
4. **TUN devices on Linux** — create a TUN manually with `ip tuntap add`
5. **X25519 ECDH + HKDF** — implement a simple key exchange in isolation
6. **pytest fixtures** — understand conftest.py and fixture scopes
7. **GitHub Actions** — create a simple workflow from scratch

---

## Quick Reference: Key Commands

```bash
# Run all tests
pytest -v

# Run single test file
pytest tests/test_crypto.py -v

# Run single test
pytest tests/test_crypto.py::TestCipher::test_encrypt_decrypt -v

# Lint check
ruff check .

# Auto-fix lint issues
ruff check --fix .

# Install package locally
pip install -e .

# Start server (requires root)
sudo python -m src.app --server 10.8.0.0/24 --ca ca.crt --cert server.crt --key server.key

# Start client (requires root)
sudo python -m src.app --remote 10.8.0.1 --ca ca.crt --cert client.crt --key client.key
```
