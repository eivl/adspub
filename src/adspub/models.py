"""Pydantic models describing the Ad Manager API version catalog."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from functools import cached_property
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

VERSION_RE = re.compile(r"^v(?P<year>\d{4})(?P<month>\d{2})$")


class VersionStatus(StrEnum):
    """Lifecycle status of an API version as seen on the public page."""

    ACTIVE = "active"
    """Listed without a deprecation marker."""

    DEPRECATED = "deprecated"
    """Listed with the "Deprecated" marker. Still callable, but scheduled for removal."""

    UNLISTED = "unlisted"
    """Not on the page at all. Assumed sunset and no longer callable."""


def normalize_version(value: str) -> str:
    """Return the canonical ``vYYYYMM`` form of a version string.

    Accepts ``v202608``, ``V202608`` and ``202608``. Raises ``ValueError`` otherwise.
    """
    candidate = value.strip()
    if candidate[:1].isdigit():
        candidate = f"v{candidate}"
    candidate = candidate.lower()
    match = VERSION_RE.match(candidate)
    if match is None:
        msg = f"invalid Ad Manager API version {value!r}; expected the form vYYYYMM"
        raise ValueError(msg)
    month = int(match["month"])
    if not 1 <= month <= 12:  # noqa: PLR2004 - calendar month bounds
        msg = f"invalid Ad Manager API version {value!r}; month must be 01-12"
        raise ValueError(msg)
    return candidate


def version_key(value: str) -> tuple[int, int]:
    """Sort key ``(year, month)`` for a canonical version string."""
    match = VERSION_RE.match(value)
    if match is None:
        msg = f"not a canonical version: {value!r}"
        raise ValueError(msg)
    return int(match["year"]), int(match["month"])


class Service(BaseModel):
    """One SOAP service exposed by an API version."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Service name, for example 'LineItemService'.")
    wsdl_url: str = Field(description="Absolute URL of the service WSDL.")
    docs_url: str | None = Field(default=None, description="Reference documentation URL.")


class ApiVersion(BaseModel):
    """One API version listed on the page."""

    model_config = ConfigDict(frozen=True)

    version: str = Field(description="Canonical version string, for example 'v202608'.")
    status: Literal[VersionStatus.ACTIVE, VersionStatus.DEPRECATED] = Field(
        description="'active' or 'deprecated'. Versions missing from the page are 'unlisted'."
    )
    services: list[Service] = Field(default_factory=list)

    @field_validator("version")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return normalize_version(value)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def year(self) -> int:
        """Release year taken from the version string."""
        return version_key(self.version)[0]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def month(self) -> int:
        """Release month taken from the version string."""
        return version_key(self.version)[1]

    @property
    def sort_key(self) -> tuple[int, int]:
        """Chronological sort key."""
        return version_key(self.version)

    @property
    def is_deprecated(self) -> bool:
        """True when the page marks this version as deprecated."""
        return self.status is VersionStatus.DEPRECATED


class VersionCheck(BaseModel):
    """Result of checking a single version against the catalog."""

    model_config = ConfigDict(frozen=True)

    version: str
    status: VersionStatus
    is_latest: bool
    latest: str = Field(description="The latest active version at the time of the check.")
    newer_versions: list[str] = Field(
        default_factory=list, description="Active versions newer than the checked one."
    )
    message: str


class Catalog(BaseModel):
    """The parsed page: every listed version with its services."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = Field(default=1, description="Format version of this document.")
    source_url: str
    fetched_at: datetime = Field(description="UTC timestamp of when the page was fetched.")
    content_sha256: str = Field(description="SHA-256 of the raw HTML the catalog came from.")
    title: str | None = Field(default=None, description="Page heading, if present.")
    versions: list[ApiVersion] = Field(
        default_factory=list, description="All listed versions, oldest first."
    )

    @field_validator("versions")
    @classmethod
    def _sort_versions(cls, value: list[ApiVersion]) -> list[ApiVersion]:
        return sorted(value, key=lambda item: item.sort_key)

    @cached_property
    def _by_version(self) -> dict[str, ApiVersion]:
        return {item.version: item for item in self.versions}

    @property
    def active(self) -> list[ApiVersion]:
        """Versions that are listed and not deprecated, oldest first."""
        return [item for item in self.versions if item.status is VersionStatus.ACTIVE]

    @property
    def deprecated(self) -> list[ApiVersion]:
        """Versions that are listed and deprecated, oldest first."""
        return [item for item in self.versions if item.status is VersionStatus.DEPRECATED]

    @property
    def latest(self) -> ApiVersion:
        """Newest active version. Raises ``LookupError`` when there is none."""
        active = self.active
        if not active:
            msg = "catalog has no active versions"
            raise LookupError(msg)
        return active[-1]

    def get(self, version: str) -> ApiVersion | None:
        """Return the listed version, or ``None`` when it is not on the page."""
        return self._by_version.get(normalize_version(version))

    def status_of(self, version: str) -> VersionStatus:
        """Status of a version; ``UNLISTED`` when it is not on the page."""
        found = self.get(version)
        return VersionStatus.UNLISTED if found is None else VersionStatus(found.status)

    def check(self, version: str) -> VersionCheck:
        """Check one version and explain the result in a single sentence."""
        canonical = normalize_version(version)
        status = self.status_of(canonical)
        latest = self.latest.version
        key = version_key(canonical)
        newer = [item.version for item in self.active if item.sort_key > key]
        is_latest = canonical == latest

        if status is VersionStatus.ACTIVE and is_latest:
            message = f"{canonical} is the latest active version."
        elif status is VersionStatus.ACTIVE:
            message = f"{canonical} is active but not the latest; {latest} is newer."
        elif status is VersionStatus.DEPRECATED:
            message = f"{canonical} is deprecated and will be removed; migrate to {latest}."
        else:
            message = f"{canonical} is not listed and is assumed to be sunset; migrate to {latest}."

        return VersionCheck(
            version=canonical,
            status=status,
            is_latest=is_latest,
            latest=latest,
            newer_versions=newer,
            message=message,
        )
