# Deployment guide

A complete walkthrough for running a PyVPN server on one machine and a client on
another: installation, certificates, every setting and its effect, and
troubleshooting. Everything below reflects the **current implementation** — see
[`ARCHITECTURE_AS_IS.md`](ARCHITECTURE_AS_IS.md) for the protocol details.

> Reminder: this project is educational and largely AI-generated. Do not use it
> to protect real traffic.

---

## 0. Requirements (both machines)

- Linux with `/dev/net/tun` (check: `ls /dev/net/tun`; if missing: `sudo modprobe tun`)
- Python 3.10+ and `iproute2` (the `ip` command)
- root privileges (TUN device + `iptables` require them)
- On the server additionally: `iptables`, an open port (default **UDP 1194**),
  and a public IP or port forwarding on the router

## 1. Installation (same on both machines)

```bash
git clone https://github.com/IExpLouDI/vpn-app-ai.git
cd vpn-app-ai
pip install .          # or: pip install -e . for development
pyvpn --help           # sanity check
```

## 2. Certificates (authenticated mode)

Generate **once, on any machine**, then distribute the files:

```bash
mkdir certs && cd certs

# 1. CA — the root of trust (needed on BOTH sides)
openssl req -x509 -newkey rsa:2048 -days 365 -nodes \
  -keyout ca.key -out ca.crt -subj "/CN=VPN-CA"

# 2. Server certificate, signed by the CA
openssl req -newkey rsa:2048 -nodes \
  -keyout server.key -out server.csr -subj "/CN=server"
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -days 365

# 3. Client certificate, signed by the same CA
openssl req -newkey rsa:2048 -nodes \
  -keyout client.key -out client.csr -subj "/CN=client"
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out client.crt -days 365
```

**File distribution:**

| File | Server | Client | Notes |
|---|---|---|---|
| `ca.crt` | yes | yes | public, any channel |
| `server.crt` + `server.key` | yes | no | private key — secure channel only (scp/ssh) |
| `client.crt` + `client.key` | no | yes | same |
| `ca.key` | no | no | keep it safe; only needed to sign new certs |

Copy to the server: `scp ca.crt server.crt server.key user@SERVER_IP:~/vpn-app-ai/`

> **Gotcha 1 — relative paths.** Certificate paths are resolved against the
> **current working directory** at launch. Either run from the directory
> containing the certs or use absolute paths.
>
> **Gotcha 2 — chain-only verification.** The implementation verifies only that
> the peer certificate is signed by the configured CA
> (`verify_certificate` in `src/crypto/certificates.py`). Expiry dates and the
> CN are **not** checked — an expired certificate still passes.

## 3. Server

### One-liner

```bash
sudo pyvpn --server 10.8.0.0/24 --ca ca.crt --cert server.crt --key server.key
```

At startup the server automatically: brings up the TUN device (`10.8.0.1`),
enables IP forwarding, adds the subnet route, and sets up **NAT**
(MASQUERADE on the default-route interface; the rule is removed on shutdown).

### Firewall

```bash
sudo ufw allow 1194/udp      # or: sudo iptables -A INPUT -p udp --dport 1194 -j ACCEPT
```

If the server sits behind NAT/a router, forward UDP 1194 to it.

### Config file (recommended for a permanent setup)

`/etc/pyvpn/server.conf`:

```ini
dev tun
proto udp
port 1194
server 10.8.0.0 255.255.255.0
ifconfig-pool 10.8.0.2 10.8.0.100
ca /etc/pyvpn/ca.crt
cert /etc/pyvpn/server.crt
key /etc/pyvpn/server.key
keepalive 10 120
verb 2
```

```bash
sudo pyvpn -c /etc/pyvpn/server.conf
```

### Optional: systemd unit

```ini
# /etc/systemd/system/pyvpn.service
[Unit]
Description=PyVPN server
After=network.target

[Service]
ExecStart=/usr/local/bin/pyvpn -c /etc/pyvpn/server.conf
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now pyvpn
```

## 4. Client

```bash
sudo pyvpn --remote SERVER_IP --ca ca.crt --cert client.crt --key client.key
```

Or `/etc/pyvpn/client.conf`:

```ini
dev tun
proto udp
remote SERVER_IP
port 1194
ca /etc/pyvpn/ca.crt
cert /etc/pyvpn/client.crt
key /etc/pyvpn/client.key
keepalive 10 120
verb 2
```

```bash
sudo pyvpn -c /etc/pyvpn/client.conf
```

The client automatically: connects, completes the handshake, receives a virtual
IP from the pool (e.g. `10.8.0.2`), configures its TUN device, and installs the
subnet route. On connection loss it **reconnects every 5 seconds** until stopped.

## 5. Verification

Expected client log:

```
Client: handshake ESTABLISHED
Data channel ready (waiting for IP assignment)
Received IP assignment: 10.8.0.2
TUN configured: 10.8.0.2/24 via tun
```

Then:

```bash
ping 10.8.0.1            # the server through the tunnel — the key test
ip addr show tun         # client's virtual IP on the interface
```

## 6. Settings reference — what affects what

| Setting | Side | Effect | When to change |
|---|---|---|---|
| `proto udp/tcp` | both | Transport. UDP is faster; TCP passes strict firewalls but TCP-over-TCP degrades on loss | Must **match on both sides** or the handshake never starts |
| `port` | both | Single port multiplexing control + data | If 1194 is taken/blocked |
| `server A.B.C.D/24` | server | VPN subnet. Server takes `.1`, clients come from the pool | **Use /24 only** — the client's subnet route is hardcoded to /24 |
| `ifconfig-pool S E` | server | Client IP range. Default: `.2`–`.254` of the subnet | To shrink/grow the address space |
| `ifconfig` | client | Nominally "static client IP"; actually a **subnet hint for route derivation** | ⚠️ Required when the server subnet is **not** `10.8.0.0/24` — otherwise the client installs a route to `10.8.0.0/24` and the tunnel is broken. Example: `ifconfig 10.9.0.2/24` for subnet `10.9.0.0/24` |
| `ca`/`cert`/`key` | both | Enable authenticated mode (**all three together**) | Without them: dev mode — encryption works, but **no authentication**; anyone can connect |
| `keepalive 10 120` | both | Server sends KEEPALIVE every 10 s; 120 s of silence = teardown. Client reconnects after timeout | Raise the timeout on flaky links |
| `comp-lzo` | either | LZ4 compression of payloads > 32 bytes. The flag only controls **sending**; any peer with `lz4` installed can decompress | The name is OpenVPN heritage — the algorithm is LZ4 |
| `redirect-gateway` | **client** | Client routes **all** traffic through the tunnel itself (default route via the server, metric 50). The server already NATs | Full-tunnel VPN. The server needs working internet egress |
| `status FILE` | **client** | OpenVPN-like status file every 10 s (bytes in/out, assigned IP). Deleted on exit | Monitoring. Does nothing on the server |
| `user nobody` | both | Drop root after setup | ⚠️ **Do not use on the server**: per-client routes are added at connect time and silently fail without root. Safe on the client (dropped after IP assignment) |
| `verb 0-4` | both | 0=WARNING, 1=INFO, 2=DEBUG (maximum). 3–4 currently map to INFO | Use 2 for debugging |
| `dev tun` | both | TUN interface name | ⚠️ On startup an existing interface with this name is **deleted** — use unique names for multiple instances |
| `cipher AES-256-GCM` | — | The only implemented cipher; no effect | Leave it alone |

Explicitly provided CLI flags override config-file values; parser defaults do
not.

## 7. Common scenarios

**Quick test without certificates (dev mode, insecure):**

```bash
sudo pyvpn --server 10.8.0.0/24                 # server
sudo pyvpn --remote SERVER_IP                   # client
```

**Full tunnel (all client internet traffic via the server):** add
`redirect-gateway` on the client.

**TCP instead of UDP:** `proto tcp` on both sides + open the TCP port.

**Custom subnet:** server `server 10.9.0.0 255.255.255.0`, and the client
**must** set `ifconfig 10.9.0.2/24` (see the settings table).

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `TUN clone device not found` | tun module missing | `sudo modprobe tun` |
| `Permission denied` on ioctl | not root | use `sudo` |
| Client stuck at `Sent HARD_RESET_CLIENT` | firewall/port/wrong IP | check `nc -u SERVER_IP 1194`, ufw, port forwarding |
| `cert verification FAILED` | cert signed by a different CA | regenerate per section 2; one CA for everyone |
| `NAT setup failed` in server log | no root or no `iptables` | sudo + install iptables; tunnel internet won't work otherwise |
| Tunnel up but no ping, subnet isn't 10.8.0.0/24 | client missing `ifconfig` | see the `ifconfig` gotcha above |
| Want packet-level insight | — | `sudo tcpdump -i tun -n` plus `verb 2` |

## 9. Honest limitations

- Educational, largely AI-generated code — **not** for production or commercial use
- Dev mode has zero authentication — local experiments only
- No handshake DoS protection, no key rotation, key material may reach swap
- Windows support is TUN-only (no routing/NAT/privilege drop)
