# Security model

## Project status

This repository is an educational VPN prototype and must not claim production-grade security unless every claim is linked to code and tests.

## Documentation rule

Every security property must be classified as one of:
- Implemented and tested
- Implemented but not fully tested
- Planned
- Not implemented

## Security properties checklist

| Property | Status | Evidence |
|---|---|---|
| Mutual authentication | Implemented | `src/protocol/control.py` (`_verify_peer_cert`); `src/protocol/tls_channel.py` (mTLS); `tests/test_handshake.py`, `tests/test_tls_channel.py` |
| Session key derivation | Implemented | `src/crypto/key_exchange.py` (HKDF + salt); `tests/test_crypto.py` |
| Replay protection | Implemented | `src/protocol/replay.py`, checked in `src/protocol/data.py`; tests `tests/test_replay.py`, `tests/test_data.py` |
| Nonce uniqueness | Implemented | `src/crypto/cipher.py` (`os.urandom(12)` per encrypt); `tests/test_crypto.py` |
| Forward secrecy | Implemented | Ephemeral X25519 in `src/crypto/key_exchange.py`; `tests/test_crypto.py::TestKeyExchange` |
| Key rotation | Planned | No rekeying/renogotiation implemented yet |
| DoS resistance on handshake | Planned | Rate limiting / handshake DoS protection not implemented |
| Privilege reduction | Partially implemented | `src/privileges.py` (`drop_privileges`/`maybe_drop_privileges`); opt-in `--user`; wired into `src/server.py` and `src/client.py`; `tests/test_privileges.py`. Per-client routes/NAT still require root. |

## Threat model questions

- What can an unauthenticated network attacker do?
- What can a replay attacker do?
- What happens if a client certificate is stolen?
- What happens if the server process crashes mid-session?
- What happens if route/NAT cleanup fails?

## Non-goals

Until verified otherwise, the repository should not claim:
- production readiness,
- audited cryptographic design,
- strong resistance to active attackers,
- hard multi-tenant isolation.
