# adspub design

Date: 2026-10-09

## Problem

Google publishes the list of supported Ad Manager (SOAP) API versions only as a
human-readable HTML page at <https://ads.google.com/apis/ads/publisher>. Versions
rotate roughly quarterly and old ones are deprecated and then removed. Nothing
machine-readable exists, so build pipelines and AI agents cannot cheaply answer
"which version should I use?" or "is the version I am pinned to still valid?".

## Goal

A small Python package, `adspub`, that

1. fetches and parses that page into a typed, stable JSON document,
2. exposes an async Python API and a Typer CLI for humans and agents,
3. caches results locally so repeated calls are cheap and work offline,
4. answers "latest version" and "status of version X" with stable exit codes.

Non-goals: calling the Ad Manager API itself, tracking the newer REST API,
scraping deprecation *dates* from developers.google.com (not on this page).

## Source page structure (observed 2026-10-09)

```
<h1>Google's DoubleClick for Publishers API</h1>
<h2>v202511 - <text style='color:#999999'>Deprecated</text></h2>
<li><a href="/apis/ads/publisher/v202511/AdjustmentService?wsdl">AdjustmentService</a>
    (<a href="https://developers.google.com/.../v202511/AdjustmentService.html">docs</a>)</li>
...
<h2>v202602</h2>
<li>...</li>
```

Versions are `v` + `YYYYMM`. A version is deprecated when its heading carries the
"Deprecated" marker. The page sends no ETag or Last-Modified, so caching is
time-based plus a content hash.

## Status model

| Status       | Meaning                                                            |
| ------------ | ------------------------------------------------------------------ |
| `active`     | Listed on the page without a deprecation marker.                   |
| `deprecated` | Listed on the page with the "Deprecated" marker. Still callable.   |
| `unlisted`   | Not on the page. Assumed removed (sunset). Treated as unusable.    |

`latest` is the active version with the highest `YYYYMM`.

## Architecture

```
src/adspub/
  models.py    Pydantic v2 models: Service, ApiVersion, Catalog, VersionCheck, LoadResult
  parser.py    HTML -> Catalog  (stdlib html.parser; no third-party HTML dependency)
  fetch.py     async httpx GET with timeout and user agent
  cache.py     JSON cache file in platformdirs user cache dir, env override
  catalog.py   load_catalog(): cache policy + fetch + stale fallback (async)
  cli.py       Typer app; every command supports --json; stable exit codes
  __main__.py  python -m adspub
```

Data flow: `load_catalog(refresh, offline, max_age)` -> read cache -> if fresh
return it -> else fetch -> parse -> write cache -> return. On network failure
with a stale cache present, return the stale cache and flag it; without any
cache, raise.

## Dependencies

Runtime: `typer`, `pydantic>=2`, `httpx`, `platformdirs`. Dev: `pytest`,
`pytest-asyncio`, `pytest-cov`, `ruff`, `mypy`, `pre-commit`.

Supported Python: 3.11 through 3.15. Managed with `uv`, built with `uv_build`.

## CLI

```
adspub latest                  print latest active version
adspub list                    table of versions with status and service count
adspub check VERSION...        status of one or more versions; exit code encodes result
adspub services VERSION        services available in a version
adspub dump [-o FILE]          full catalog as JSON
adspub parse FILE              parse a local HTML copy (or - for stdin)
adspub schema                  JSON Schema of the catalog document
adspub cache path|info|clear   inspect or clear the cache
```

Global options: `--json`, `--refresh`, `--offline`, `--max-age SECONDS`,
`--url`, `--cache-dir`, `--version`.

Exit codes: `0` success / all checked versions active, `10` at least one
checked version deprecated, `20` at least one checked version unlisted,
`1` runtime error (network, parse), `2` usage error (from Click).

## Caching

File: `<user cache dir>/adspub/catalog.json` (override with `ADSPUB_CACHE_DIR`
or `--cache-dir`). Default max age 24 hours. JSON output carries `source`
(`network` | `cache` | `stale-cache`) and `fetched_at` so an agent can tell how
fresh the answer is.

## Testing

Unit tests against a checked-in HTML fixture (parser, models, status logic),
cache round-trip in a temp dir, catalog loading with `httpx.MockTransport`,
CLI via Typer's `CliRunner`. A scheduled GitHub Actions job parses the live page
weekly to detect format drift.

## Release

GitHub Actions: CI (ruff, mypy, pytest matrix 3.11-3.15), publish to PyPI via
trusted publishing on `v*` tags, after the user has tested the interface.
