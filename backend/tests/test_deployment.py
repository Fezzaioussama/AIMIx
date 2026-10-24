"""What a deployment relies on: the public health probe and serving the built app."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from config.settings import pin_settings
from tests.conftest import TEST_SETTINGS

INDEX_HTML = '<!doctype html><div id="root"></div>'


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    """A stand-in for frontend/dist after `npm run build`."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(INDEX_HTML)
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log('app')")
    (tmp_path / "logo.png").write_bytes(b"png")
    (tmp_path.parent / "secret.txt").write_text("outside the build")
    return tmp_path


@pytest.fixture
def site(dist: Path) -> Iterator[TestClient]:
    pin_settings(TEST_SETTINGS.model_copy(update={"frontend_dist_dir": str(dist)}))
    try:
        with TestClient(create_app()) as client:
            yield client
    finally:
        pin_settings(TEST_SETTINGS)


def test_health_is_public(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_responses_have_browser_security_boundaries(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"
    assert "object-src 'none'" in response.headers["content-security-policy"]
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"


def test_without_a_build_only_the_api_is_served(client: TestClient) -> None:
    assert client.get("/chat").status_code == 404


def test_client_routes_get_the_app_shell(site: TestClient) -> None:
    for path in ("/", "/chat", "/settings"):
        response = site.get(path)
        assert response.status_code == 200
        assert response.text == INDEX_HTML
        assert response.headers["cache-control"] == "no-cache"


def test_bundle_files_are_served_and_cached_for_good(site: TestClient) -> None:
    response = site.get("/assets/index-abc123.js")
    assert response.status_code == 200
    assert "immutable" in response.headers["cache-control"]
    assert site.get("/logo.png").headers["cache-control"] == "no-cache"


def test_api_paths_never_fall_back_to_the_app(site: TestClient) -> None:
    response = site.get("/api/no-such-route")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"
    assert site.get("/api/health").json() == {"status": "ok"}


def test_files_outside_the_build_are_not_served(site: TestClient) -> None:
    response = site.get("/..%2Fsecret.txt")
    assert "outside the build" not in response.text


def test_a_missing_build_fails_at_startup(tmp_path: Path) -> None:
    pin_settings(TEST_SETTINGS.model_copy(update={"frontend_dist_dir": str(tmp_path)}))
    try:
        with pytest.raises(RuntimeError, match=r"index\.html"):
            create_app()
    finally:
        pin_settings(TEST_SETTINGS)
