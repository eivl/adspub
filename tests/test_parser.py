from __future__ import annotations

import pytest

from adspub.models import VersionStatus
from adspub.parser import ParseError, parse_catalog

URL = "https://ads.google.com/apis/ads/publisher"


def test_parses_fixture(page_html: str) -> None:
    catalog = parse_catalog(page_html, source_url=URL)
    assert catalog.title == "Google's DoubleClick for Publishers API"
    assert len(catalog.versions) == 4
    assert catalog.versions[0].status is VersionStatus.DEPRECATED
    assert all(v.status is VersionStatus.ACTIVE for v in catalog.versions[1:])
    assert len(catalog.content_sha256) == 64
    # every version on this page exposes the same set of services
    counts = {len(v.services) for v in catalog.versions}
    assert len(counts) == 1
    assert counts.pop() == 43


def test_service_links_are_absolute(page_html: str) -> None:
    catalog = parse_catalog(page_html, source_url=URL)
    service = catalog.versions[-1].services[0]
    assert service.name == "AdjustmentService"
    assert service.wsdl_url == f"{URL}/v202608/AdjustmentService?wsdl"
    assert service.docs_url is not None
    assert service.docs_url.startswith("https://developers.google.com/")


def test_minimal_page() -> None:
    html = """
    <html><body><h1>Title</h1>
    <h2>v202501 - <text>Deprecated</text></h2>
    <li><a href="/apis/ads/publisher/v202501/FooService?wsdl">FooService</a></li>
    <h2>v202505</h2>
    <li><a href="/apis/ads/publisher/v202505/FooService?wsdl">FooService</a>
        (<a href="https://example.com/docs">docs</a>)</li>
    </body></html>
    """
    catalog = parse_catalog(html, source_url=URL)
    assert [v.version for v in catalog.versions] == ["v202501", "v202505"]
    assert catalog.versions[0].status is VersionStatus.DEPRECATED
    assert catalog.versions[0].services[0].docs_url is None
    assert catalog.versions[1].services[0].docs_url == "https://example.com/docs"


def test_deprecated_marker_is_case_insensitive() -> None:
    html = "<h2>v202501 - DEPRECATED</h2><li><a href='/x?wsdl'>X</a></li>"
    catalog = parse_catalog(html, source_url=URL)
    assert catalog.versions[0].status is VersionStatus.DEPRECATED


def test_versions_are_sorted_even_if_page_is_not() -> None:
    html = "<h2>v202505</h2><h2>v202501</h2>"
    catalog = parse_catalog(html, source_url=URL)
    assert [v.version for v in catalog.versions] == ["v202501", "v202505"]


def test_no_versions_raises() -> None:
    with pytest.raises(ParseError, match="no version headings"):
        parse_catalog("<html><body><h1>Oops</h1></body></html>", source_url=URL)


def test_heading_without_version_raises() -> None:
    with pytest.raises(ParseError, match="could not find"):
        parse_catalog("<h2>Something else</h2>", source_url=URL)


def test_service_before_heading_raises() -> None:
    with pytest.raises(ParseError, match="before any version heading"):
        parse_catalog("<li><a href='/x?wsdl'>X</a></li><h2>v202501</h2>", source_url=URL)


def test_items_without_links_are_ignored() -> None:
    html = "<h2>v202501</h2><li>plain text</li><li><a href='/x?wsdl'>X</a></li>"
    catalog = parse_catalog(html, source_url=URL)
    assert [s.name for s in catalog.versions[0].services] == ["X"]
