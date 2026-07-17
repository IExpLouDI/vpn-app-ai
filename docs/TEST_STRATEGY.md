# Test strategy

## Objectives

The repository should support three independent confidence levels:
1. unit correctness,
2. integration correctness,
3. privileged system correctness.

## Test layers

### Unit tests
No root privileges required.

Cover:
- config parsing,
- frame/packet parsing,
- message serialization,
- key derivation,
- nonce handling,
- session state transitions,
- replay-window logic.

### Integration tests
Linux runner preferred, root optional depending on approach.

Cover:
- client/server handshake,
- encrypted data exchange,
- fragmentation/reassembly,
- reconnect logic,
- graceful shutdown.

### System tests
Linux only, root required.

Cover:
- TUN creation,
- interface configuration,
- route programming,
- NAT setup and cleanup.

## CI expectations

Current reality (`.github/workflows/python-ci.yml`): a single job runs on both
pull requests and pushes to `main`:

- `ruff check .` (lint),
- `pytest -v --tb=short` — all non-privileged tests (unit + integration;
  `tests/legacy/` is excluded via `pyproject.toml`),
- packaging smoke test (`pip install -e .` + import check).

### Manual or protected workflow
Run:
- privileged system tests (`tests/legacy/`, root + TUN).

Planned: split PR/main pipelines and add an automated privileged system-test
job (see README status matrix, "Integration CI (privileged)").

## Rules

- No test should rely on hardcoded local absolute paths.
- Privileged tests must be clearly marked and skippable.
- Security properties must have explicit tests.
