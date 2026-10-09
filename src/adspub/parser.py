"""Parse the HTML of the Ad Manager API version page into a ``Catalog``.

The page is tiny and hand-written (an ``<h2>`` per version followed by ``<li>``
items with a WSDL link and a docs link), so the standard library parser is
enough and avoids a third-party HTML dependency.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin

from adspub.models import VERSION_RE, ApiVersion, Catalog, Service, VersionStatus

DEPRECATED_MARKER = "deprecated"


class ParseError(ValueError):
    """Raised when the page does not look like the version list we expect."""


@dataclass
class _PendingVersion:
    version: str
    heading_text: list[str] = field(default_factory=list)
    services: list[Service] = field(default_factory=list)

    def status(self) -> VersionStatus:
        text = "".join(self.heading_text).lower()
        if DEPRECATED_MARKER in text:
            return VersionStatus.DEPRECATED
        return VersionStatus.ACTIVE


@dataclass
class _PendingService:
    name: str = ""
    wsdl_href: str | None = None
    docs_href: str | None = None
    current_href: str | None = None
    current_text: list[str] = field(default_factory=list)


class _PageParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title_parts: list[str] = []
        self.versions: list[_PendingVersion] = []
        self._in_title = False
        self._in_heading = False
        self._item: _PendingService | None = None

    # -- tag handlers -------------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "h1":
            self._in_title = True
        elif tag == "h2":
            self._in_heading = True
            self.versions.append(_PendingVersion(version=""))
        elif tag == "li":
            self._item = _PendingService()
        elif tag == "a" and self._item is not None:
            href = dict(attrs).get("href")
            self._item.current_href = href
            self._item.current_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1":
            self._in_title = False
        elif tag == "h2":
            self._in_heading = False
        elif tag == "a" and self._item is not None:
            self._finish_link()
        elif tag == "li":
            self._finish_item()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        elif self._in_heading and self.versions:
            self.versions[-1].heading_text.append(data)
        elif self._item is not None and self._item.current_href is not None:
            self._item.current_text.append(data)

    # -- helpers ------------------------------------------------------------

    def _finish_link(self) -> None:
        item = self._item
        if item is None or item.current_href is None:
            return
        text = "".join(item.current_text).strip()
        href = urljoin(self.base_url, item.current_href)
        if text.lower() == "docs":
            item.docs_href = href
        elif item.wsdl_href is None:
            item.name = text
            item.wsdl_href = href
        item.current_href = None
        item.current_text = []

    def _finish_item(self) -> None:
        item = self._item
        self._item = None
        if item is None or not item.name or item.wsdl_href is None:
            return
        if not self.versions:
            msg = f"service {item.name!r} appears before any version heading"
            raise ParseError(msg)
        self.versions[-1].services.append(
            Service(name=item.name, wsdl_url=item.wsdl_href, docs_url=item.docs_href)
        )


def _heading_version(pending: _PendingVersion) -> str:
    text = "".join(pending.heading_text)
    for token in text.replace("-", " ").split():
        if VERSION_RE.match(token.lower()):
            return token.lower()
    msg = f"could not find a vYYYYMM version in heading {text.strip()!r}"
    raise ParseError(msg)


def parse_catalog(
    html: str,
    *,
    source_url: str,
    fetched_at: datetime | None = None,
) -> Catalog:
    """Parse page HTML into a ``Catalog``.

    Raises ``ParseError`` when no version headings are found, so a redesigned
    page fails loudly instead of silently reporting "no versions".
    """
    parser = _PageParser(base_url=source_url)
    parser.feed(html)
    parser.close()

    if not parser.versions:
        msg = "no version headings found; the page format may have changed"
        raise ParseError(msg)

    versions = [
        ApiVersion(version=_heading_version(p), status=p.status(), services=p.services)
        for p in parser.versions
    ]
    title = "".join(parser.title_parts).strip() or None

    return Catalog(
        source_url=source_url,
        fetched_at=fetched_at or datetime.now(UTC),
        content_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
        title=title,
        versions=versions,
    )
