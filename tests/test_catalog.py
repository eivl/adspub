from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from adspub.cache import read_cache, write_cache
from adspub.catalog import Source, load_catalog
from adspub.fetch import DEFAULT_URL, FetchError, fetch_catalog, fetch_html
from adspub.models import Catalog
from tests.conftest import make_client


async def test_fetch_html_and_catalog(page_html: str) -> None:
    calls: list[str] = []
    async with make_client(page_html, calls=calls) as client:
        html = await fetch_html(client=client)
        assert html == page_html
        catalog = await fetch_catalog(client=client)
    assert calls == [DEFAULT_URL, DEFAULT_URL]
    assert catalog.latest.version == "v202608"
    assert catalog.source_url == DEFAULT_URL


async def test_fetch_http_error(page_html: str) -> None:
    async with make_client(page_html, status=503) as client:
        with pytest.raises(FetchError, match="HTTP 503"):
            await fetch_html(client=client)


async def test_fetch_transport_error() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as client:
        with pytest.raises(FetchError, match="failed"):
            await fetch_html(client=client)


async def test_load_fetches_and_caches(cache_dir: Path, page_html: str) -> None:
    calls: list[str] = []
    async with make_client(page_html, calls=calls) as client:
        first = await load_catalog(client=client)
        assert first.source is Source.NETWORK
        assert first.cache_age_seconds == 0

        second = await load_catalog(client=client)
        assert second.source is Source.CACHE
        assert second.catalog == first.catalog
    assert calls == [DEFAULT_URL]
    assert await read_cache() == first.catalog


async def test_load_refresh_bypasses_cache(cache_dir: Path, page_html: str) -> None:
    calls: list[str] = []
    async with make_client(page_html, calls=calls) as client:
        await load_catalog(client=client)
        result = await load_catalog(client=client, refresh=True)
    assert result.source is Source.NETWORK
    assert len(calls) == 2


async def test_load_expired_cache_refetches(
    cache_dir: Path, catalog: Catalog, page_html: str
) -> None:
    await write_cache(catalog)
    later = catalog.fetched_at + timedelta(days=2)
    calls: list[str] = []
    async with make_client(page_html, calls=calls) as client:
        result = await load_catalog(client=client, now=later)
    assert result.source is Source.NETWORK
    assert calls == [DEFAULT_URL]


async def test_load_offline_uses_any_cache(
    cache_dir: Path, catalog: Catalog, page_html: str
) -> None:
    await write_cache(catalog)
    later = catalog.fetched_at + timedelta(days=30)
    calls: list[str] = []
    async with make_client(page_html, calls=calls) as client:
        result = await load_catalog(client=client, offline=True, now=later)
    assert result.source is Source.CACHE
    assert result.cache_age_seconds == pytest.approx(30 * 86400)
    assert calls == []


async def test_load_offline_without_cache_fails(cache_dir: Path, page_html: str) -> None:
    async with make_client(page_html) as client:
        with pytest.raises(FetchError, match="offline"):
            await load_catalog(client=client, offline=True)


async def test_load_stale_fallback(
    cache_dir: Path, catalog: Catalog, page_html: str, capsys: pytest.CaptureFixture[str]
) -> None:
    await write_cache(catalog)
    later = catalog.fetched_at + timedelta(days=2)
    async with make_client(page_html, status=500) as client:
        result = await load_catalog(client=client, now=later)
    assert result.source is Source.STALE_CACHE
    assert result.warning is not None
    assert "HTTP 500" in result.warning
    assert "warning" in capsys.readouterr().err


async def test_load_stale_fallback_disabled(
    cache_dir: Path, catalog: Catalog, page_html: str
) -> None:
    await write_cache(catalog)
    later = catalog.fetched_at + timedelta(days=2)
    async with make_client(page_html, status=500) as client:
        with pytest.raises(FetchError):
            await load_catalog(client=client, now=later, allow_stale=False)


async def test_load_network_failure_without_cache(cache_dir: Path, page_html: str) -> None:
    async with make_client(page_html, status=500) as client:
        with pytest.raises(FetchError):
            await load_catalog(client=client)


async def test_load_result_is_serialisable(cache_dir: Path, page_html: str) -> None:
    async with make_client(page_html) as client:
        result = await load_catalog(client=client, now=datetime.now(UTC))
    data = result.model_dump(mode="json")
    assert data["source"] == "network"
    assert data["catalog"]["versions"][-1]["version"] == "v202608"
