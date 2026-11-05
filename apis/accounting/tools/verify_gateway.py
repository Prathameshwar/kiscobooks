"""Run the checked-in gateway configuration in an isolated nginx process with local stubs."""

import json
import os
import socket
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[3]
BINARY = Path(os.environ["ACCOUNTING_TEST_NGINX_BINARY"])
original: list[str | None] = []


class Identity(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 -- HTTP server interface
        assert self.path == "/internal/v1/gateway/authorize"
        original.append(self.headers.get("X-Original-URI"))
        assert self.headers.get("X-Actor-Context") is None
        if self.headers.get("Authorization") == "Bearer unavailable":
            self.send_response(503)
        elif self.headers.get("Authorization") == "Bearer forbidden":
            self.send_response(403)
        elif self.headers.get("Authorization") == "Bearer allowed":
            self.send_response(204)
            for name in (
                "Actor-Context",
                "Actor-Signature",
                "Company-Context",
                "Company-Signature",
            ):
                self.send_header("X-" + name, "trusted-" + name)
        else:
            self.send_response(401)
        self.end_headers()

    def log_message(self, message: str, *args: Any) -> None:
        pass


class Accounting(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 -- HTTP server interface
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"path": self.path, "headers": dict(self.headers)}).encode())

    def log_message(self, message: str, *args: Any) -> None:
        pass


def main() -> None:
    identity = ThreadingHTTPServer(("127.0.0.1", 0), Identity)
    accounting = ThreadingHTTPServer(("127.0.0.1", 0), Accounting)
    for server in (identity, accounting):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    runtime = ROOT / ".test_artifacts" / ("accounting-nginx-" + uuid.uuid4().hex)
    (runtime / "logs").mkdir(parents=True)
    (runtime / "temp").mkdir()
    (runtime / "conf.d").mkdir()
    (runtime / "conf.d/proxy.include").write_text(
        (ROOT / "start/win/conf/proxy.include").read_text()
    )
    config = (ROOT / "start/win/conf/bill.conf").read_text()
    config = config.replace("listen       8090", f"listen       127.0.0.1:{port}")
    config = config.replace("127.0.0.1:8001", f"127.0.0.1:{identity.server_port}")
    config = config.replace("127.0.0.1:8011", f"127.0.0.1:{accounting.server_port}")
    (runtime / "bill.conf").write_text(config)
    (runtime / "nginx.conf").write_text(
        "worker_processes 1; pid logs/nginx.pid; error_log logs/error.log;\n"
        "events { worker_connections 64; }\nhttp { access_log off; include bill.conf; }\n"
    )
    args = [str(BINARY), "-p", str(runtime) + os.sep, "-c", "nginx.conf"]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    subprocess.run([*args, "-t"], check=True, creationflags=flags, capture_output=True)  # noqa: S603 -- explicit local test executable
    process = subprocess.Popen(args, creationflags=flags)  # noqa: S603 -- isolated nginx test
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=3) as client:
            for _ in range(50):
                try:
                    if client.get("/nginx-health").status_code == 200:
                        break
                except httpx.HTTPError:
                    time.sleep(0.1)
            path = "/accounting/v1/companies/01900000-0000-7000-8000-000000000001/parties?limit=2"
            for token, status in [(None, 401), ("forbidden", 403), ("unavailable", 503)]:
                h = {"X-Actor-Context": "forged"}
                if token:
                    h["Authorization"] = "Bearer " + token
                response = client.get(path, headers=h)
                assert response.status_code == status, (response.status_code, response.text)
                assert set(response.json()) == {"error"}
            h = {"Authorization": "Bearer allowed"}
            for name in (
                "Actor-Context",
                "Actor-Signature",
                "Company-Context",
                "Company-Signature",
            ):
                h["X-" + name] = "forged"
            response = client.get(path, headers=h)
            assert response.status_code == 200, response.text
            assert response.json()["path"] == path.removeprefix("/accounting")
            for name in (
                "Actor-Context",
                "Actor-Signature",
                "Company-Context",
                "Company-Signature",
            ):
                assert response.json()["headers"]["X-" + name] == "trusted-" + name
            assert original[-1] == path
            assert client.get("/accounting/health/live").status_code == 200
            assert client.get("/identity/internal/v1/gateway/authorize").status_code == 404
            print("PASS: gateway authentication, signed forwarding and protected internal routes")
    finally:
        subprocess.run([*args, "-s", "quit"], check=True, creationflags=flags, capture_output=True)  # noqa: S603 -- stop only this owned nginx process
        process.wait(timeout=10)
        identity.shutdown()
        accounting.shutdown()


if __name__ == "__main__":
    main()
