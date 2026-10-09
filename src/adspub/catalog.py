"""High-level entry point combining cache policy and network fetching."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field

from adspub.cache import cache_age, read_cache, write_cache
from adspub.fetch import DEFAULT_TIMEOUT, DEFAULT_URL, FetchError, fetch_catalog
from adspub.models import Catalog

DEFAULT_MAX_AGE = 24 * 60 * 60
"""Default cache lifetime in seconds (24 hours)."""


class Source(StrEnum):
    """Where a loaded catalog came from."""

    NETWORK = "network"
    CACHE = "cache"
    STALE_CACHE = "stale-cache"
    """Returned when the network failed and an expired cache was used instead."""


class LoadResult(BaseModel):
    """A catalog plus provenance, so callers can judge how fresh it is."""

    model_config = ConfigDict(frozen=True)

    catalog: Catalog
    source: Source
    cache_age_seconds: float = Field(ge=0)
    warning: str | None = None


def _warn(message: str) -> None:
    print(f"adspub: warning: {message}", file=sys.stderr)


async def load_catalog(
    *,
    url: str = DEFAULT_URL,
    refresh: bool = False,
    offline: bool = False,
    max_age: float = DEFAULT_MAX_AGE,
    cache_dir: Path | None = None,
    client: httpx.AsyncClient | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    allow_stale: bool = True,
    now: datetime | None = None,
) -> LoadResult:
    """Return the catalog, using the cache when it is fresh enough.

    Policy, in order:

    1. ``offline``: use the cache regardless of age; fail if there is none.
    2. Cache younger than ``max_age`` and not ``refresh``: use it.
    3. Fetch from the network and update the cache.
    4. If the fetch fails and a cache exists and ``allow_stale``: return the
       stale cache with ``source="stale-cache"`` and a warning.
    5. Otherwise raise ``FetchError``.
    """
    current = now or datetime.now(UTC)
    cached = await read_cache(cache_dir)
    age = cache_age(cached, current) if cached is not None else 0.0

    if offline:
        if cached is None:
            msg = "offline mode requested but no cache exists"
            raise FetchError(msg)
        return LoadResult(catalog=cached, source=Source.CACHE, cache_age_seconds=age)

    if cached is not None and not refresh and age <= max_age:
        return LoadResult(catalog=cached, source=Source.CACHE, cache_age_seconds=age)

    try:
        fresh = await fetch_catalog(url, client=client, timeout=timeout)
    except FetchError as exc:
        if cached is None or not allow_stale:
            raise
        warning = f"{exc}; using cached data from {cached.fetched_at.isoformat()}"
        _warn(warning)
        return LoadResult(
            catalog=cached, source=Source.STALE_CACHE, cache_age_seconds=age, warning=warning
        )

    await write_cache(fresh, cache_dir)
    return LoadResult(catalog=fresh, source=Source.NETWORK, cache_age_seconds=0.0)
