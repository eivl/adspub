from __future__ import annotations

import pytest

from adspub.models import ApiVersion, Catalog, VersionStatus, normalize_version, version_key


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("v202608", "v202608"),
        ("V202608", "v202608"),
        ("202608", "v202608"),
        ("  v202602 ", "v202602"),
    ],
)
def test_normalize_version_accepts_common_forms(raw: str, expected: str) -> None:
    assert normalize_version(raw) == expected


@pytest.mark.parametrize("raw", ["", "v2026", "v20260", "v202613", "v202600", "latest", "2026-08"])
def test_normalize_version_rejects_garbage(raw: str) -> None:
    with pytest.raises(ValueError, match="invalid Ad Manager API version"):
        normalize_version(raw)


def test_version_key_orders_chronologically() -> None:
    assert version_key("v202511") < version_key("v202602") < version_key("v202608")


def test_catalog_sorts_versions_and_exposes_year_month(catalog: Catalog) -> None:
    assert [v.version for v in catalog.versions] == ["v202511", "v202602", "v202605", "v202608"]
    first = catalog.versions[0]
    assert (first.year, first.month) == (2025, 11)
    assert first.model_dump()["year"] == 2025


def test_catalog_active_deprecated_latest(catalog: Catalog) -> None:
    assert [v.version for v in catalog.deprecated] == ["v202511"]
    assert [v.version for v in catalog.active] == ["v202602", "v202605", "v202608"]
    assert catalog.latest.version == "v202608"


def test_catalog_get_and_status_of(catalog: Catalog) -> None:
    assert catalog.get("202608") is not None
    assert catalog.get("v209901") is None
    assert catalog.status_of("v202608") is VersionStatus.ACTIVE
    assert catalog.status_of("v202511") is VersionStatus.DEPRECATED
    assert catalog.status_of("v202408") is VersionStatus.UNLISTED


def test_check_latest(catalog: Catalog) -> None:
    result = catalog.check("v202608")
    assert result.status is VersionStatus.ACTIVE
    assert result.is_latest
    assert result.newer_versions == []
    assert "latest" in result.message


def test_check_active_but_old(catalog: Catalog) -> None:
    result = catalog.check("v202602")
    assert result.status is VersionStatus.ACTIVE
    assert not result.is_latest
    assert result.newer_versions == ["v202605", "v202608"]
    assert result.latest == "v202608"


def test_check_deprecated(catalog: Catalog) -> None:
    result = catalog.check("v202511")
    assert result.status is VersionStatus.DEPRECATED
    assert result.newer_versions == ["v202602", "v202605", "v202608"]
    assert "deprecated" in result.message


def test_check_unlisted(catalog: Catalog) -> None:
    result = catalog.check("v202405")
    assert result.status is VersionStatus.UNLISTED
    assert "sunset" in result.message


def test_latest_without_active_versions_raises() -> None:
    catalog = Catalog(
        source_url="x",
        fetched_at="2026-01-01T00:00:00Z",
        content_sha256="0" * 64,
        versions=[ApiVersion(version="v202511", status=VersionStatus.DEPRECATED)],
    )
    with pytest.raises(LookupError):
        _ = catalog.latest


def test_catalog_json_round_trip(catalog: Catalog) -> None:
    restored = Catalog.model_validate_json(catalog.model_dump_json())
    assert restored == catalog
