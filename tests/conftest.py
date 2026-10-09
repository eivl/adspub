from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from adspub.fetch import DEFAULT_URL
from adspub.models import Catalog
from adspub.parser import parse_catalog

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def page_html() -> str:
    return (FIXTURES / "publisher.html").read_text(encoding="utf-8")


@pytest.fixture
def catalog(page_html: str) -> Catalog:
    return parse_catalog(
        page_html,
        source_url=DEFAULT_URL,
        fetched_at=datetime(2026, 10, 9, 12, 0, tzinfo=UTC),
    )


@pytest.fixture
def cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "cache"
    monkeypatch.setenv("ADSPUB_CACHE_DIR", str(directory))
    return directory


def make_client(
    page_html: str, *, status: int = 200, calls: list[str] | None = None
) -> httpx.AsyncClient:
    """An httpx client whose transport serves the fixture without touching the network."""

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(request.url))
        if status != 200:
            return httpx.Response(status)
        return httpx.Response(200, text=page_html, headers={"content-type": "text/html"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))
