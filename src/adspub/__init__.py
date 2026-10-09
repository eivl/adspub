"""Machine-readable view of the Google Ad Manager API version list."""

from importlib.metadata import PackageNotFoundError, version

from adspub.catalog import DEFAULT_MAX_AGE, LoadResult, load_catalog
from adspub.fetch import DEFAULT_URL, FetchError, fetch_catalog, fetch_html
from adspub.models import (
    ApiVersion,
    Catalog,
    Service,
    VersionCheck,
    VersionStatus,
)
from adspub.parser import ParseError, parse_catalog

try:
    __version__ = version("adspub")
except PackageNotFoundError:  # pragma: no cover - only when running from a bare checkout
    __version__ = "0.0.0"

__all__ = [
    "DEFAULT_MAX_AGE",
    "DEFAULT_URL",
    "ApiVersion",
    "Catalog",
    "FetchError",
    "LoadResult",
    "ParseError",
    "Service",
    "VersionCheck",
    "VersionStatus",
    "__version__",
    "fetch_catalog",
    "fetch_html",
    "load_catalog",
    "parse_catalog",
]
