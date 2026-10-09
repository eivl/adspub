from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from adspub.cache import (
    cache_age,
    cache_path,
    clear_cache,
    default_cache_dir,
    read_cache,
    write_cache,
)
from adspub.models import Catalog


def test_default_cache_dir_honours_env(cache_dir: Path) -> None:
    assert default_cache_dir() == cache_dir
    assert cache_path() == cache_dir / "catalog.json"


def test_default_cache_dir_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADSPUB_CACHE_DIR", raising=False)
    # platformdirs nests the app name differently per OS (Windows adds a Cache suffix)
    assert "adspub" in default_cache_dir().parts


async def test_round_trip(cache_dir: Path, catalog: Catalog) -> None:
    assert await read_cache() is None
    path = await write_cache(catalog)
    assert path == cache_dir / "catalog.json"
    assert await read_cache() == catalog
    assert not list(cache_dir.glob(".catalog-*.tmp"))


async def test_explicit_dir(tmp_path: Path, catalog: Catalog) -> None:
    other = tmp_path / "elsewhere"
    await write_cache(catalog, other)
    assert (other / "catalog.json").exists()
    assert await read_cache(other) == catalog


async def test_corrupt_cache_is_ignored(cache_dir: Path) -> None:
    cache_dir.mkdir()
    (cache_dir / "catalog.json").write_text("{not json")
    assert await read_cache() is None


async def test_clear(cache_dir: Path, catalog: Catalog) -> None:
    assert await clear_cache() is False
    await write_cache(catalog)
    assert await clear_cache() is True
    assert await read_cache() is None


def test_cache_age(catalog: Catalog) -> None:
    now = catalog.fetched_at + timedelta(hours=2)
    assert cache_age(catalog, now) == 7200.0
    assert cache_age(catalog, catalog.fetched_at - timedelta(seconds=5)) == 0.0


def test_cache_age_naive_timestamp(catalog: Catalog) -> None:
    naive = catalog.model_copy(update={"fetched_at": datetime(2026, 10, 9, 12, 0)})  # noqa: DTZ001
    assert cache_age(naive, datetime(2026, 10, 9, 13, 0, tzinfo=UTC)) == 3600.0
