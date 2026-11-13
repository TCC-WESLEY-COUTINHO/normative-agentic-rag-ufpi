"""The configured dev healthcheck must run with the service image's executables."""

import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
import yaml


def test_dev_service_healthcheck_command_is_executable():
    compose = Path(__file__).resolve().parents[2] / "compose.yaml"
    command = yaml.safe_load(compose.read_text(encoding="utf-8"))["services"]["agent_service"][
        "healthcheck"
    ]["test"]
    assert command[0] == "CMD"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        target = f"http://127.0.0.1:{server.server_port}"
        actual = [part.replace("http://localhost:8080", target) for part in command[1:]]
        try:
            result = subprocess.run(actual, capture_output=True, text=True, timeout=10)
        except FileNotFoundError:
            pytest.fail(f"Configured healthcheck executable is missing: {actual[0]}")
        assert result.returncode == 0, result.stderr
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
