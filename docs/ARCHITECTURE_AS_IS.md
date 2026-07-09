# Architecture as-is

This document describes the repository **as currently implemented**, not the intended end state.

## Purpose

The project is an educational VPN prototype inspired by OpenVPN concepts:
- virtual tunnel interface,
- separate control/data concerns,
- encrypted packet forwarding,
- client/server topology.

## Important note

If README and code diverge, this document must be treated as the authoritative **as-built** description.

## Current architecture documentation rules

For every subsystem, describe:
1. What is implemented now.
2. What is partially implemented.
3. What is planned only.
4. What assumptions exist (Linux-only, root required, iptables required, etc.).

## Suggested sections

### Transport
Describe the actual network transport modes currently implemented.

### Control plane
Describe the actual handshake/session establishment behavior currently implemented.

### Data plane
Describe the actual packet encapsulation, encryption, fragmentation, and replay behavior currently implemented.

### OS integration
Describe:
- TUN lifecycle,
- route management,
- NAT/iptables usage,
- privilege requirements.

### Failure handling
Describe:
- reconnect behavior,
- keepalive behavior,
- cleanup semantics,
- shutdown behavior.

## Constraints

- Linux-only behavior should be marked explicitly.
- Privileged operations must be listed explicitly.
- Any security property must reference tests and source files.
