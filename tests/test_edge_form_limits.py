"""Exercise the real upstream form parser before upload-field validation."""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import httpx2
import pytest
from fastapi.testclient import TestClient

from voices.edge.app import create_edge_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    library = tmp_path / "voices"
    out_dir = tmp_path / "outputs"
    app = create_edge_app(library=library, out_dir=out_dir)
    with (
        patch("voices.edge.app.review_clone_upload") as review,
        patch("voices.edge.app.load_batch_design") as batch,
        TestClient(app, base_url="http://127.0.0.1:8765") as test_client,
    ):
        yield test_client
    review.assert_not_called()
    batch.assert_not_called()
    assert not library.exists()
    assert not out_dir.exists()


def test_testclient_uses_supported_httpx2_transport(client: TestClient):
    assert isinstance(client, httpx2.Client)
    response = client.get("/api/ui-config")
    assert isinstance(response, httpx2.Response)
    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/api/clone/review", "/api/design/batch"])
@pytest.mark.parametrize("declared_length", [True, False], ids=["content-length", "chunked"])
@pytest.mark.parametrize(
    ("body", "detail"),
    [
        pytest.param(
            b"&".join([b"unused=x"] * 1001),
            "Too many fields. Maximum number of fields is 1000.",
            id="field-count",
        ),
        pytest.param(
            b"x=" + b"a" * (1024 * 1024),
            "Field exceeded maximum size of 1024KB.",
            id="field-value-size",
        ),
        pytest.param(
            b"x" * (1024 * 1024 + 1) + b"=",
            "Field exceeded maximum size of 1024KB.",
            id="field-name-size",
        ),
    ],
)
def test_urlencoded_limits_precede_required_upload_validation(
    client: TestClient, path: str, declared_length: bool, body: bytes, detail: str
):
    # File/Form endpoints still parse URL-encoded bodies, despite requiring an
    # UploadFile. These requests bypass the multipart Content-Length preflight.
    request = client.build_request(
        "POST",
        path,
        content=body if declared_length else iter([body]),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert ("content-length" in request.headers) is declared_length
    response = client.send(request)

    assert response.status_code == 400
    assert response.json() == {"error_code": "RequestValidationError", "detail": detail}


@pytest.mark.parametrize(("path", "upload"), [("/api/clone/review", "audio"), ("/api/design/batch", "file")])
@pytest.mark.parametrize(
    "body",
    [
        pytest.param(b"language=English", id="ordinary-form"),
        pytest.param(b"&".join([b"unused=x"] * 1000), id="field-count-boundary"),
        pytest.param(b"x=" + b"a" * (1024 * 1024 - 1), id="field-size-boundary"),
    ],
)
def test_urlencoded_within_limits_reaches_required_upload_validation(
    client: TestClient, path: str, upload: str, body: bytes
):
    response = client.post(path, content=body, headers={"Content-Type": "application/x-www-form-urlencoded"})

    assert response.status_code == 400
    payload = response.json()
    assert payload["error_code"] == "RequestValidationError"
    assert upload in payload["detail"]
    assert "Field required" in payload["detail"]
    assert "Too many fields" not in payload["detail"]
    assert "exceeded maximum size" not in payload["detail"]
