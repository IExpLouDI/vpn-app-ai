"""Integration tests: TCP mode, LZO compression, status file, ping."""
import subprocess
import sys
import os
import time
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

CERTS = ["--ca", "certs/ca.crt", "--cert", "certs/client.crt", "--key", "certs/client.key"]
SERVER_CERTS = ["--ca", "certs/ca.crt", "--cert", "certs/server.crt", "--key", "certs/server.key"]
ROOT = "/home/vssuchkov/vpn-app"
PYTHON = sys.executable
BASE = [PYTHON, "-m", "src.app", "--verb", "1"]


def run(args, cwd=ROOT, label=""):
    proc = subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if label:
        print(f"  {label} PID={proc.pid}")
    return proc


def wait_for_ping(target, count=3, timeout=10):
    r = subprocess.run(
        ["ping", "-c", str(count), target],
        capture_output=True, text=True, timeout=timeout,
    )
    return r.returncode == 0


def test_udp_cert():
    print("\n--- UDP with certs ---")
    s = run(BASE + ["--dev", "tun10", "--server", "10.10.0.0/24"] + SERVER_CERTS, label="server")
    time.sleep(1)
    if s.poll() is not None:
        return "server_failed"
    c = run(BASE + ["--dev", "tun11", "--remote", "127.0.0.1"] + CERTS, label="client")
    time.sleep(3)
    if c.poll() is not None:
        return "client_failed"
    try:
        ok = wait_for_ping("10.10.0.2", 2) and wait_for_ping("10.10.0.1", 2)
        return "pass" if ok else "ping_fail"
    finally:
        s.terminate()
        c.terminate()
        s.wait(timeout=3)
        c.wait(timeout=3)


def test_tcp_cert():
    print("\n--- TCP with certs ---")
    s = run(BASE + ["--dev", "tun12", "--server", "10.12.0.0/24", "--proto", "tcp"] + SERVER_CERTS, label="server")
    time.sleep(1)
    if s.poll() is not None:
        return "server_failed"
    c = run(BASE + ["--dev", "tun13", "--remote", "127.0.0.1", "--proto", "tcp"] + CERTS, label="client")
    time.sleep(3)
    if c.poll() is not None:
        return "client_failed"
    try:
        ok = wait_for_ping("10.12.0.2", 2) and wait_for_ping("10.12.0.1", 2)
        return "pass" if ok else "ping_fail"
    finally:
        s.terminate()
        c.terminate()
        s.wait(timeout=3)
        c.wait(timeout=3)


def test_lzo_compression():
    print("\n--- LZO compression ---")
    s = run(BASE + ["--dev", "tun14", "--server", "10.14.0.0/24", "--comp-lzo"] + SERVER_CERTS, label="server")
    time.sleep(1)
    if s.poll() is not None:
        return "server_failed"
    c = run(BASE + ["--dev", "tun15", "--remote", "127.0.0.1", "--comp-lzo"] + CERTS, label="client")
    time.sleep(3)
    if c.poll() is not None:
        return "client_failed"
    try:
        ok = wait_for_ping("10.14.0.2", 2) and wait_for_ping("10.14.0.1", 2)
        return "pass" if ok else "ping_fail"
    finally:
        s.terminate()
        c.terminate()
        s.wait(timeout=3)
        c.wait(timeout=3)


def test_status_file():
    print("\n--- Status file ---")
    with tempfile.NamedTemporaryFile(suffix=".status", delete=False) as f:
        status_path = f.name

    s = run(BASE + ["--dev", "tun16", "--server", "10.16.0.0/24"] + SERVER_CERTS, label="server")
    time.sleep(1)
    if s.poll() is not None:
        os.unlink(status_path)
        return "server_failed"
    c = run(BASE + ["--dev", "tun17", "--remote", "127.0.0.1", "--status", status_path] + CERTS, label="client")
    time.sleep(4)
    if c.poll() is not None:
        os.unlink(status_path)
        return "client_failed"
    try:
        ok = wait_for_ping("10.16.0.2", 2) and wait_for_ping("10.16.0.1", 2)
        if not ok:
            return "ping_fail"

        with open(status_path) as f:
            content = f.read()
        print(f"  status file ({len(content)} bytes)")

        checks = (
            "OpenVPN CLIENT LIST" in content
            and "GLOBAL STATS" in content
            and "10.16.0.2" in content
        )
        return "pass" if checks else "status_bad"
    finally:
        s.terminate()
        c.terminate()
        s.wait(timeout=3)
        c.wait(timeout=3)
        try:
            os.unlink(status_path)
        except OSError:
            pass


def test_multi_client():
    print("\n--- Multi-client (UDP + certs) ---")
    s = run(BASE + ["--dev", "tun18", "--server", "10.18.0.0/24", "--ifconfig-pool", "10.18.0.2-10.18.0.10"] + SERVER_CERTS, label="server")
    time.sleep(1)
    if s.poll() is not None:
        return "server_failed"
    c1 = run(BASE + ["--dev", "tun19", "--remote", "127.0.0.1"] + CERTS, label="client1")
    time.sleep(1)
    c2 = run(BASE + ["--dev", "tun20", "--remote", "127.0.0.1"] + CERTS, label="client2")
    time.sleep(3)
    if c1.poll() is not None or c2.poll() is not None:
        return "client_failed"
    try:
        ok = (wait_for_ping("10.18.0.1", 2)
              and wait_for_ping("10.18.0.2", 2)
              and wait_for_ping("10.18.0.3", 2))
        return "pass" if ok else "ping_fail"
    finally:
        s.terminate()
        c1.terminate()
        c2.terminate()
        s.wait(timeout=3)
        c1.wait(timeout=3)
        c2.wait(timeout=3)


def main():
    tests = [
        ("udp_cert", test_udp_cert),
        ("tcp_cert", test_tcp_cert),
        ("lzo", test_lzo_compression),
        ("status_file", test_status_file),
        ("multi_client", test_multi_client),
    ]

    results = {}
    for name, fn in tests:
        try:
            results[name] = fn()
        except Exception as e:
            results[name] = f"error: {e}"

    print("\n=== RESULTS ===")
    all_pass = True
    for name, status in results.items():
        ok = status == "pass"
        if not ok:
            all_pass = False
        print(f"  {name}: {'PASS' if ok else 'FAIL'} ({status})")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
