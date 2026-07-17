# Backlog

**This is the single source of truth for remaining work.** The README status
matrix describes what exists; this file describes what to do next. Items are
grouped by priority; each entry lists the affected code and a suggested approach.

Effort tags: **S** = hours, **M** = a day or two, **L** = multi-day.

---

## P1 — Security-critical, low effort

### 1. Handshake DoS protection
- **Where:** `src/server.py` (`_get_or_create_session`, `handle_udp_data`),
  `src/protocol/control.py`
- **Problem:** every `HARD_RESET_CLIENT` datagram allocates a `Session` with a
  fresh X25519 keypair — unauthenticated resource exhaustion. Cleanup happens
  only after `HANDSHAKE_TIMEOUT` (30 s).
- **Approach:** cap concurrent non-established sessions; per-source-IP handshake
  rate limit; optionally an OpenVPN-style cookie round (server echoes a token in
  `HARD_RESET_SERVER` that the client must present).
- **Tests:** unit tests for the limiter; flood simulation without root.
- **Effort:** M

### 2. Certificate expiry validation
- **Where:** `src/crypto/certificates.py` (`verify_certificate`),
  `tests/test_crypto.py`
- **Problem:** only the CA signature chain is verified; an expired (or
  not-yet-valid) certificate passes. Documented as a gotcha in
  `DEPLOYMENT.md`, but it should be fixed, not documented.
- **Approach:** check `not_valid_before_utc`/`not_valid_after_utc` against
  `datetime.now(UTC)`; optionally enforce a CN policy (e.g. server certs must
  have `CN=server`). Keep behavior configurable to not break dev mode.
- **Effort:** S

### 3. Client subnet route hardcoded to /24
- **Where:** `src/client.py` (`_handle_ip_assign`), `src/server.py`
  (`_assign_ip_to_client`)
- **Problem:** the client derives the subnet route as `x.y.z.0/24` and the
  server IP as `.1`, so non-/24 subnets require the `ifconfig` hint hack
  (documented in `DEPLOYMENT.md`).
- **Approach:** send the assigned address with its prefix in `IP_ASSIGN`
  (e.g. `10.9.0.7/24` instead of a bare IP — the server knows the prefixlen);
  derive the route from the real network address. Remove the `ifconfig`
  workaround from the docs afterwards.
- **Effort:** S–M

---

## P2 — Protocol completeness

### 4. Key rotation / renegotiation
- **Where:** `src/protocol/control.py`, `src/protocol/data.py`
- **Problem:** one session key for the whole session lifetime; a long-lived
  tunnel has a single point of compromise.
- **Approach:** periodic rekey (e.g. every N minutes or M packets): fresh
  ephemeral X25519 exchange inside the established encrypted channel, swap
  `Cipher` atomically, reset the replay window. Alternatively full
  re-handshake on a timer.
- **Effort:** L

### 5. SHUTDOWN message
- **Where:** `src/protocol/messages.py` (defined, unused), `src/client.py`
  (`stop`), `src/server.py` (`stop`, `_remove_client`)
- **Problem:** teardown is implicit — the peer notices only after
  `keepalive_timeout` (up to 120 s of stale state).
- **Approach:** send `SHUTDOWN` from `stop()` paths; on receipt, tear down the
  session immediately (release IP, remove routes, close writer). Already
  documented as unused in README; wire it or remove it.
- **Effort:** S

### 6. Memory locking for key material (`mlock`)
- **Where:** `src/crypto/cipher.py`, `src/protocol/control.py`
- **Problem:** the 32-byte session key lives in ordinary heap memory and can
  reach swap.
- **Approach:** allocate the key buffer with `mlock(2)` (ctypes, Linux-only,
  graceful fallback elsewhere); zero it on session teardown.
- **Effort:** M

---

## P3 — Testing & ops

### 7. Privileged integration CI
- **Where:** `.github/workflows/`, `tests/legacy/`
- **Problem:** root + TUN system tests run only manually.
- **Approach:** separate workflow job with `sudo` (GitHub runners allow it):
  TUN creation, interface config, route/NAT setup and cleanup. Gate `main`
  merges on it; keep PRs on the fast unprivileged suite.
- **Effort:** M

### 8. `tests/legacy/` audit
- **Where:** `tests/legacy/`
- **Problem:** excluded from pytest (`pyproject.toml`) and ruff; unknown whether
  they still pass after recent refactors (dev-mode handshake, NAT wiring).
- **Approach:** run them manually with root, fix or delete; mark with
  `pytest.mark.privileged` and auto-skip without root so they can live in the
  main suite.
- **Effort:** M

### 9. TCP transport end-to-end test
- **Where:** `tests/` (new), `src/protocol/framing.py`, `src/client.py`,
  `src/server.py`
- **Problem:** integration tests cover the handshake logic but not the TCP
  framing path (`frame_packet`/`read_frame` through real streams).
- **Approach:** loopback TCP test without TUN: handshake + data roundtrip over
  framed streams.
- **Effort:** S

### 10. Server-side status file
- **Where:** `src/status.py`, `src/server.py`
- **Problem:** status output is client-only; on a server the `status` directive
  is silently ignored.
- **Approach:** extend `StatusFile` with a server view (connected clients,
  virtual IPs, per-client byte counters — data lives in `self.clients`).
- **Effort:** M

### 11. Certificate generation script
- **Where:** new `certs/generate.sh` (tracked as ❌ Planned in README)
- **Problem:** the openssl recipe from `DEPLOYMENT.md` is manual and error-prone.
- **Approach:** script CA + server + N client cert generation with sane
  defaults and an output layout matching the deployment guide.
- **Effort:** S

---

## P4 — Platform & hygiene

### 12. Windows full support
- **Where:** `src/tun_windows.py`, `src/routing.py`, `src/privileges.py`
- **Problem:** TUN-only; no routing, NAT, or privilege handling on Windows.
- **Effort:** L

### 13. `verb 3–4` are no-ops
- **Where:** `src/app.py` (`setup_logging`)
- **Problem:** levels map `{0: WARNING, 1: INFO, 2: DEBUG}`; 3–4 fall back to
  INFO, so `verb 3` in `examples/*.conf` is cosmetic.
- **Approach:** either add finer levels (e.g. 3 = DEBUG + packet dumps) or clamp
  the accepted range and docs to 0–2.
- **Effort:** S

### 14. Dual import scheme (`src.*` vs top-level)
- **Where:** all of `src/`, `tests/conftest.py`, `setup.py`
- **Problem:** modules import each other as top-level (`from config import ...`)
  while tests import them as `src.*` — two module identities; works only with an
  (editable) install putting `src/` on `sys.path`. Already bit us once with a
  stale site-packages copy.
- **Approach:** make `src/` a proper package (relative imports everywhere) and
  install it as such; or drop the `src.*` test imports. Touches everything —
  do it in isolation.
- **Effort:** M

---

## Rules for this file

- Completed items are **deleted** from this file (git history keeps them).
- New gaps found in code review are added here first, then fixed.
- README's ❌ Planned rows mirror the relevant items above; when an item ships,
  update both.
