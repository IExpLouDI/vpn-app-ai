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

### Pull requests
Run:
- lint,
- unit tests,
- packaging smoke test.

### Main branch
Run:
- lint,
- unit tests,
- integration tests.

### Manual or protected workflow
Run:
- privileged system tests.

## Rules

- No test should rely on hardcoded local absolute paths.
- Privileged tests must be clearly marked and skippable.
- Security properties must have explicit tests.
