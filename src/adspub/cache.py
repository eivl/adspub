"""On-disk JSON cache for a parsed ``Catalog``.

The cache is a single file. Reads and writes are small, so they are run in a
worker thread to keep the public API non-blocking.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from platformdirs import user_cache_dir
from pydantic import ValidationError

from adspub.models import Catalog

APP_NAME = "adspub"
ENV_CACHE_DIR = "ADSPUB_CACHE_DIR"
CACHE_FILENAME = "catalog.json"


def default_cache_dir() -> Path:
    """Cache directory: ``$ADSPUB_CACHE_DIR`` or the platform user cache dir."""
    override = os.environ.get(ENV_CACHE_DIR)
    if override:
        return Path(override).expanduser()
    return Path(user_cache_dir(APP_NAME))


def cache_path(cache_dir: Path | None = None) -> Path:
    """Full path of the cache file."""
    return (cache_dir or default_cache_dir()) / CACHE_FILENAME


def _read_sync(path: Path) -> Catalog | None:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    try:
        return Catalog.model_validate_json(raw)
    except ValidationError:
        return None


def _write_sync(path: Path, catalog: Catalog) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = catalog.model_dump_json(indent=2).encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".catalog-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _clear_sync(path: Path) -> bool:
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


async def read_cache(cache_dir: Path | None = None) -> Catalog | None:
    """Return the cached catalog, or ``None`` if missing or unreadable."""
    return await asyncio.to_thread(_read_sync, cache_path(cache_dir))


async def write_cache(catalog: Catalog, cache_dir: Path | None = None) -> Path:
    """Atomically write the catalog to the cache file and return its path."""
    path = cache_path(cache_dir)
    await asyncio.to_thread(_write_sync, path, catalog)
    return path


async def clear_cache(cache_dir: Path | None = None) -> bool:
    """Delete the cache file. Returns ``True`` if a file was removed."""
    return await asyncio.to_thread(_clear_sync, cache_path(cache_dir))


def cache_age(catalog: Catalog, now: datetime | None = None) -> float:
    """Seconds since the catalog was fetched."""
    current = now or datetime.now(UTC)
    fetched = catalog.fetched_at
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=UTC)
    return max(0.0, (current - fetched).total_seconds())
