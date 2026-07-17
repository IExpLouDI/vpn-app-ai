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
| TUN interface management | Implemented | `src/tun.py` (`TunInterface` open/set_ip/set_mtu/close lifecycle). Requires Linux `/dev/net/tun` + `CAP_NET_ADMIN`/root; Windows via `src/tun_windows.py` (partial). |
| Encrypted data channel | Implemented | `src/protocol/data.py` (`DataChannel`), `src/crypto/cipher.py` (AES-256-GCM); `tests/test_data.py`, `tests/test_crypto.py`. |
| TLS 1.3 control channel | Implemented | `src/protocol/tls_channel.py`; `tests/test_tls_channel.py`. Mutual TLS 1.3 over TCP. Note: module is not yet wired as the default server/client control path (the running VPN still uses the custom X25519 ECDH handshake in `src/protocol/control.py`). |
| mTLS certificate validation | Implemented | Enforced in `src/protocol/tls_channel.py` (`_make_server_context`/`_make_client_context`): server requires a client cert and verifies it against the CA; client verifies the server cert against the CA. Covered by `tests/test_tls_channel.py`. |
| Replay protection | Implemented | `src/protocol/replay.py` (sliding bitmask `ReplayWindow`) wired into `src/protocol/data.py` `DataChannel.decrypt`; `tests/test_replay.py`, `tests/test_data.py` (`test_replay_detection`, `test_out_of_window_rejected`). |
| NAT / masquerade | Implemented | `src/routing.py` (`setup_nat`/`teardown_nat` via `iptables MASQUERADE`), wired into `src/server.py` startup/shutdown; outbound interface auto-detected from the default route (`get_default_interface`). Requires root/`iptables`; not exercised by CI (needs privileges). |
| Dev mode (no certificates) | Implemented | `src/protocol/control.py`: certless peers are accepted only when no CA is configured; auth-configured peers reject certless counterparts. `tests/test_handshake.py` (`test_dev_mode_handshake`, `test_auth_server_rejects_certless_client`, `test_auth_client_rejects_certless_server`). |
| Client auto-reconnect | Implemented | `src/client.py` (`VpnClient.run` retry loop). Reconnect semantics are best-effort; see `docs/TEST_STRATEGY.md`. |
| Fragmentation / reassembly | Implemented | `src/protocol/data.py` (`DataChannel.encrypt`/`decrypt` fragment groups); `tests/test_data.py::test_fragmentation`. MTU assumed 1500. |
| Config file & CLI precedence | Implemented | `src/config.py` (OpenVPN-style parser incl. `status` directive), `src/cli.py` (only explicitly provided flags override file values); `proto`/`port`/`verb` validated in `Config.__post_init__`. `tests/test_config.py`, `tests/test_cli.py`. |
| Status file | Implemented | Client-only: `src/status.py`, wired into `src/client.py`; enabled via `--status` or the `status` config directive. `tests/test_status.py`. |
| Integration tests | Partial | Unit/integration tests in `tests/` run without root. Privileged system tests live in `tests/legacy/` and require root + TUN; see `docs/TEST_STRATEGY.md`. |
| Production readiness | Not implemented | Repository is educational / prototype grade; largely AI-generated (see README disclaimer). |

## Rules for updating this file

- Every new feature must update this matrix.
- Every “Implemented” status must reference:
  - source files,
  - tests,
  - operational constraints.
- Security claims must never be marked “Implemented” without a test reference.
