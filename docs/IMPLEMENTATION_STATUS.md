# Implementation status

This document describes the **current repository state**.

## Status labels

- Implemented
- Partially implemented
- Planned
- Not implemented
- Needs verification

## Capability matrix

| Capability | Status | Notes |
|---|---|---|
| TUN interface management | Needs verification | Confirm create/configure/destroy lifecycle and Linux assumptions. |
| Encrypted data channel | Needs verification | Document cipher, nonce lifecycle, key derivation, and tests. |
| TLS 1.3 control channel | Implemented | `src/protocol/tls_channel.py`; `tests/test_tls_channel.py`. TCP control channel with mutual TLS 1.3 (server `CERT_REQUIRED`, client verifies server cert against CA). Data key transported over the authenticated channel. |
| mTLS certificate validation | Implemented | Enforced in `src/protocol/tls_channel.py` (`_make_server_context`/`_make_client_context`): server requires a client cert and verifies it against the CA; client verifies the server cert against the CA. Covered by `tests/test_tls_channel.py`. |
| Replay protection | Needs verification | Must reference packet-window logic and dedicated tests. |
| NAT / masquerade | Needs verification | Document where it is configured and how cleanup is handled. |
| Client auto-reconnect | Needs verification | Describe real reconnect semantics and failure modes. |
| Fragmentation / reassembly | Needs verification | Add MTU assumptions and coverage notes. |
| Integration tests | Partial | Explain prerequisites, OS constraints, and exact scenarios. |
| Production readiness | Not implemented | Repository is educational / prototype grade unless proven otherwise. |

## Rules for updating this file

- Every new feature must update this matrix.
- Every “Implemented” status must reference:
  - source files,
  - tests,
  - operational constraints.
- Security claims must never be marked “Implemented” without a test reference.
