"""Integration test: multi-client VPN with inter-client ping."""
import subprocess
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def run_process(args, cwd, label):
    proc = subprocess.Popen(
        args, cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    print(f"  {label} PID={proc.pid}")
    return proc


def main():
    root = "/home/vssuchkov/vpn-app"
    python = sys.executable

    base = [python, "-m", "src.app", "--verb", "1"]

    server_args = base + [
        "--dev", "tun0",
        "--server", "10.8.0.0/24",
        "--ifconfig-pool", "10.8.0.2-10.8.0.100",
        "--ca", "certs/ca.crt",
        "--cert", "certs/server.crt",
        "--key", "certs/server.key",
    ]

    client1_args = base + [
        "--dev", "tun1",
        "--remote", "127.0.0.1",
        "--ca", "certs/ca.crt",
        "--cert", "certs/client.crt",
        "--key", "certs/client.key",
    ]

    client2_args = base + [
        "--dev", "tun2",
        "--remote", "127.0.0.1",
        "--ca", "certs/ca.crt",
        "--cert", "certs/client.crt",
        "--key", "certs/client.key",
    ]

    processes = []

    try:
        print("Starting server...")
        server = run_process(server_args, root, "server")
        processes.append(server)
        time.sleep(1)
        if server.poll() is not None:
            print("Server failed:", server.stdout.read().decode())
            return 1

        print("Starting client 1...")
        c1 = run_process(client1_args, root, "client1")
        processes.append(c1)
        time.sleep(1)
        if c1.poll() is not None:
            print("Client 1 failed:", c1.stdout.read().decode())
            return 1

        print("Starting client 2...")
        c2 = run_process(client2_args, root, "client2")
        processes.append(c2)
        time.sleep(2)
        if c2.poll() is not None:
            print("Client 2 failed:", c2.stdout.read().decode())
            return 1

        print("\nAll processes running. Testing...\n")

        results = {}

        # Client 1 -> Server
        r = subprocess.run(
            ["ping", "-c", "2", "10.8.0.1"],
            capture_output=True, text=True, timeout=10,
        )
        results["Client1->Server"] = r.returncode == 0

        # Client 2 -> Server
        r = subprocess.run(
            ["ping", "-c", "2", "10.8.0.1"],
            capture_output=True, text=True, timeout=10,
        )
        results["Client2->Server"] = r.returncode == 0

        # Server -> Client 1
        r = subprocess.run(
            ["ping", "-c", "2", "10.8.0.2"],
            capture_output=True, text=True, timeout=10,
        )
        results["Server->Client1"] = r.returncode == 0

        # Server -> Client 2
        r = subprocess.run(
            ["ping", "-c", "2", "10.8.0.3"],
            capture_output=True, text=True, timeout=10,
        )
        results["Server->Client2"] = r.returncode == 0

        print("Results:")
        all_pass = True
        for name, ok in results.items():
            status = "PASS" if ok else "FAIL"
            if not ok:
                all_pass = False
            print(f"  {name}: {status}")

        if all_pass:
            print("\n=== MULTI-CLIENT TEST PASSED ===")
            return 0
        else:
            print("\n=== SOME TESTS FAILED ===")
            return 1

    finally:
        for p in processes:
            p.terminate()
        for p in processes:
            try:
                p.wait(timeout=3)
            except Exception:
                p.kill()


if __name__ == "__main__":
    sys.exit(main())
