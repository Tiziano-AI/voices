"""Exercise raw local headers through the real edge admission boundary."""

import socket
import threading
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from starlette.types import Receive, Scope, Send

from voices.edge.app import LaunchOptions, create_edge_app, launch_edge_server


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_edge_app(library=tmp_path / "library", out_dir=tmp_path / "outputs")
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        yield client


@pytest.mark.parametrize(
    "origin",
    [
        "",
        "null",
        "http://[",
        "http://localhost:",
        "http://localhost:0",
        "http://localhost:65536",
        "http://localhost:notaport",
        "http://localhost:８７６５",
        "http://localhost:+8765",
        "http://localhost:8765/",
        "http://localhost:8765/path",
        "http://localhost:8765?",
        "http://localhost:8765?x=1",
        "http://localhost:8765#",
        "http://localhost:8765#x",
        "http://user@localhost:8765",
        "http://user:pass@localhost:8765",
        "https://localhost:8765",
        "http://localhost:8766",
        "http://localhost",
        "http://localhost:8765,http://localhost:8765",
        "http://localhost:8765 http://localhost:8765",
        "http://localhost.evil:8765",
        "http://2130706433:8765",
        "http://127.0.0.2:8765",
        "http://[::ffff:127.0.0.1]:8765",
        " http://localhost:8765",
        "http://localhost:8765 ",
        "http://localhost:8765\t",
        "http://local\thost:8765",
        "http://localhost:8765\r",
        "http://localhost:8765\n",
        "http://localhost:8765\x00",
        "http://localhost:8765\x7f",
    ],
)
def test_malformed_origins_reject_before_mutation(client: TestClient, origin: str):
    response = client.post("/api/operations/probe/cancel", headers={"Origin": origin.encode("utf-8")})

    assert response.status_code == 400
    assert response.json()["error_code"] == "InvalidInputError"
    assert not client.app.state.context.cancellations.is_cancelled("probe")


@pytest.mark.parametrize(
    "host",
    [
        "",
        "testserver",
        "evil.example:8765",
        "localhost.evil:8765",
        "127.0.0.2:8765",
        "localhost",
        "localhost:",
        "localhost:0",
        "localhost:65536",
        "localhost:8766",
        "localhost:notaport",
        "localhost:+8765",
        "localhost:８７６５",
        "[",
        "::1:8765",
        "localhost:8765/",
        "localhost:8765?",
        "localhost:8765#",
        "user@localhost:8765",
        "localhost:8765,localhost:8765",
        " localhost:8765",
        "localhost:8765\t",
    ],
)
def test_malformed_hosts_reject_before_library_read(client: TestClient, host: str):
    with patch("voices.edge.app.list_voice_summaries") as read_library:
        response = client.get("/api/voices", headers={"Host": host.encode("utf-8")})

    assert response.status_code == 400
    assert response.json()["error_code"] == "InvalidInputError"
    read_library.assert_not_called()


def test_missing_host_is_rejected(tmp_path: Path):
    app = create_edge_app(library=tmp_path / "library", out_dir=tmp_path / "outputs")

    async def without_transport_host(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            # TestClient invents a Host when absent, so remove it at its ASGI seam.
            scope["headers"] = [(key, value) for key, value in scope["headers"] if key != b"host"]
        await app(scope, receive, send)

    with TestClient(without_transport_host, base_url="http://127.0.0.1:8765") as client:
        response = client.get("/api/ui-config")

    assert response.status_code == 400
    assert response.json()["error_code"] == "InvalidInputError"


@pytest.mark.parametrize("header", ["Host", "Origin"])
def test_duplicate_local_headers_are_rejected(client: TestClient, header: str):
    value = "localhost:8765" if header == "Host" else "http://localhost:8765"
    response = client.post("/api/operations/probe/cancel", headers=[(header, value), (header, value)])

    assert response.status_code == 400
    assert not client.app.state.context.cancellations.is_cancelled("probe")


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]", "LOCALHOST"])
@pytest.mark.parametrize("origin_host", ["localhost", "127.0.0.1", "[::1]", "LOCALHOST"])
def test_loopback_aliases_share_the_actual_listener(client: TestClient, host: str, origin_host: str):
    response = client.post(
        "/api/operations/probe/cancel",
        headers={"Host": f"{host}:8765", "Origin": f"http://{origin_host}:8765"},
    )

    assert response.status_code == 204
    assert client.app.state.context.cancellations.is_cancelled("probe")


@pytest.mark.parametrize("port", ["", ":80", ":000080"])
def test_default_http_port_is_accepted(tmp_path: Path, port: str):
    app = create_edge_app(library=tmp_path / "library", out_dir=tmp_path / "outputs")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.post(
            "/api/operations/probe/cancel",
            headers={"Host": f"[::1]{port}", "Origin": f"http://localhost{port}"},
        )

    assert response.status_code == 204


def test_local_client_without_origin_is_accepted(client: TestClient):
    assert client.post("/api/operations/probe/cancel").status_code == 204


def test_matching_host_and_origin_cannot_override_socket_port(client: TestClient):
    response = client.post(
        "/api/operations/probe/cancel",
        headers={"Host": "localhost:9999", "Origin": "http://localhost:9999"},
    )

    assert response.status_code == 400
    assert not client.app.state.context.cancellations.is_cancelled("probe")


def test_forwarded_headers_do_not_change_admission(client: TestClient):
    response = client.post(
        "/api/operations/probe/cancel",
        headers={
            "Origin": "http://localhost:8765",
            "X-Forwarded-Host": "evil.example:443",
            "X-Forwarded-Proto": "https",
            "Forwarded": 'for=203.0.113.1;host="evil.example:443";proto=https',
        },
    )

    assert response.status_code == 204


def test_launcher_disables_proxy_header_trust(tmp_path: Path):
    with patch("voices.edge.app.resolve_web_dist", return_value=None), patch("voices.edge.app.uvicorn.run") as run:
        launch_edge_server(
            library=tmp_path / "library",
            out_dir=tmp_path / "outputs",
            launch=LaunchOptions(host="::1", port=8765, open_browser=False),
        )
    assert run.call_args.kwargs["host"] == "::1"
    assert run.call_args.kwargs["proxy_headers"] is False


def test_reference_audio_response_uses_captured_bytes(client: TestClient):
    with patch("voices.edge.app.reference_audio_bytes", return_value=b"captured-reference") as capture:
        response = client.get("/api/voices/fixture_voice/reference-audio")

    assert response.status_code == 200
    assert response.content == b"captured-reference"
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["content-disposition"] == 'attachment; filename="fixture_voice-reference.wav"'
    assert capture.call_args.args[1] == "fixture_voice"


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
def test_real_listener_uses_socket_not_host_or_forwarded_headers(tmp_path: Path, host: str):
    ready = threading.Event()

    class ReadyServer(uvicorn.Server):
        async def startup(self, sockets: list[socket.socket] | None = None) -> None:
            await super().startup(sockets)
            ready.set()

    app = create_edge_app(library=tmp_path / "library", out_dir=tmp_path / "outputs")
    server = ReadyServer(uvicorn.Config(app, log_level="error", proxy_headers=False))
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family) as listener:
        listener.bind((host, 0))
        port = listener.getsockname()[1]
        worker = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        worker.start()
        try:
            assert ready.wait(timeout=5), "Local fixture server did not start."
            authority = f"[{host}]" if ":" in host else host
            with httpx.Client(base_url=f"http://{authority}:{port}", trust_env=False) as client:
                allowed = client.post(
                    "/api/operations/probe/cancel",
                    headers={"Origin": f"http://localhost:{port}", "X-Forwarded-Proto": "https"},
                )
                rejected = client.post(
                    "/api/operations/rejected/cancel",
                    headers={"Host": "localhost:1", "Origin": "http://localhost:1"},
                )
                rejected_read = client.get("/api/voices", headers={"Host": f"evil.example:{port}"})
            assert allowed.status_code == 204
            assert rejected.status_code == 400
            assert rejected.json()["error_code"] == "InvalidInputError"
            assert rejected_read.status_code == 400
            assert not app.state.context.cancellations.is_cancelled("rejected")
            assert not (tmp_path / "library").exists()
        finally:
            server.should_exit = True
            worker.join(timeout=5)
            assert not worker.is_alive(), "Local fixture server did not stop."
