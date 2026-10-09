"""Async HTTP fetching of the version page."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from adspub.models import Catalog
from adspub.parser import parse_catalog

DEFAULT_URL = "https://ads.google.com/apis/ads/publisher"
DEFAULT_TIMEOUT = 15.0
USER_AGENT = "adspub (+https://github.com/eivl/adspub)"


class FetchError(RuntimeError):
    """Raised when the page cannot be downloaded."""


async def fetch_html(
    url: str = DEFAULT_URL,
    *,
    client: httpx.AsyncClient | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """Download the page and return its HTML. Raises ``FetchError`` on failure."""
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}
    try:
        if client is not None:
            response = await client.get(url, headers=headers, timeout=timeout)
        else:
            async with httpx.AsyncClient(follow_redirects=True) as owned:
                response = await owned.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        msg = f"GET {url} returned HTTP {exc.response.status_code}"
        raise FetchError(msg) from exc
    except httpx.HTTPError as exc:
        msg = f"GET {url} failed: {exc}"
        raise FetchError(msg) from exc
    return response.text


async def fetch_catalog(
    url: str = DEFAULT_URL,
    *,
    client: httpx.AsyncClient | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Catalog:
    """Download and parse the page. No caching."""
    fetched_at = datetime.now(UTC)
    html = await fetch_html(url, client=client, timeout=timeout)
    return parse_catalog(html, source_url=url, fetched_at=fetched_at)
