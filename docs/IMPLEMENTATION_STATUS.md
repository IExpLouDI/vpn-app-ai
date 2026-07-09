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
| TLS 1.3 control channel | Planned unless proven in code | README currently describes it strongly; code and tests should be linked here. |
| mTLS certificate validation | Needs verification | Document exact certificate chain validation logic. |
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
