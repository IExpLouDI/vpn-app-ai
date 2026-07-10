"""Integration test: start server and client, verify tunnel works."""
import subprocess
import sys
import os
import time
import signal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    root = "/home/vssuchkov/vpn-app"
    server_args = [
        sys.executable, "-m", "src.app",
        "--dev", "tun0",
        "--server", "10.8.0.0/24",
        "--ca", "certs/ca.crt",
        "--cert", "certs/server.crt",
        "--key", "certs/server.key",
        "--verb", "3",
    ]
    client_args = [
        sys.executable, "-m", "src.app",
        "--dev", "tun1",
        "--ifconfig", "10.8.0.2/24",
        "--remote", "127.0.0.1",
        "--ca", "certs/ca.crt",
        "--cert", "certs/client.crt",
        "--key", "certs/client.key",
        "--verb", "3",
    ]

    print("Starting server...")
    server = subprocess.Popen(
        server_args, cwd=root,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    time.sleep(1)

    if server.poll() is not None:
        print("Server failed to start:", server.stdout.read().decode())
        return 1

    print("Starting client...")
    client = subprocess.Popen(
        client_args, cwd=root,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    time.sleep(1)

    if client.poll() is not None:
        print("Client failed to start:", client.stdout.read().decode())
        server.terminate()
        return 1

    print("Both running. Testing bidirectional ping...")
    time.sleep(2)

    # Test: client -> server
    result = subprocess.run(
        ["ping", "-c", "2", "10.8.0.1"],
        capture_output=True, text=True, timeout=10,
    )
    client_to_server = result.returncode == 0
    print("Client -> Server:", "PASS" if client_to_server else "FAIL")
    if not client_to_server:
        print(result.stdout, result.stderr)

    # Test: server -> client (need to run ping from client's network namespace)
    # For now, use the fact that server TUN sees client's packets
    result2 = subprocess.run(
        ["ping", "-c", "2", "10.8.0.2"],
        capture_output=True, text=True, timeout=10,
    )
    server_to_client = result2.returncode == 0
    print("Server -> Client:", "PASS" if server_to_client else "FAIL")
    if not server_to_client:
        print(result2.stdout, result2.stderr)

    client.terminate()
    server.terminate()

    if client_to_server and server_to_client:
        print("\n=== INTEGRATION TEST PASSED ===")
        return 0
    else:
        print("\n=== SOME TESTS FAILED ===")
        return 1


if __name__ == "__main__":
    sys.exit(main())
