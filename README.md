# adspub

[![PyPI](https://img.shields.io/pypi/v/adspub.svg)](https://pypi.org/project/adspub/)
[![Python](https://img.shields.io/pypi/pyversions/adspub.svg)](https://pypi.org/project/adspub/)
[![CI](https://github.com/eivl/adspub/actions/workflows/ci.yml/badge.svg)](https://github.com/eivl/adspub/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Machine-readable view of the Google Ad Manager API version list, with a CLI
built for both humans and AI agents.

Google only publishes which Ad Manager (formerly DoubleClick for Publishers)
API versions are supported on a human-readable page:
<https://ads.google.com/apis/ads/publisher>. Versions rotate several times a
year, get marked deprecated, and then disappear. `adspub` turns that page into
JSON, caches it locally, and answers two questions reliably:

- Which version is the latest?
- Is the version I am pinned to still active, deprecated, or gone?

![adspub demo](https://raw.githubusercontent.com/eivl/adspub/main/demo/demo.gif)

Status rules:

| Status       | Meaning                                                             |
| ------------ | ------------------------------------------------------------------- |
| `active`     | Listed on the page without a deprecation marker. Safe to use.       |
| `deprecated` | Listed with the "Deprecated" marker. Still callable, migrate soon.  |
| `unlisted`   | Not on the page at all. Assumed sunset and no longer callable.      |

## Install

```sh
uv tool install adspub        # as a global CLI tool
uvx adspub latest             # or run without installing
pip install adspub            # or into a project
```

Supports Python 3.11 through 3.15.

## Human usage

```sh
adspub latest                       # v202608
adspub list                         # table of all versions with status
adspub check v202602                # active, deprecated or unlisted
adspub check v202511 v202602        # several at once; worst status sets the exit code
adspub services v202608             # SOAP services and WSDL/doc links in a version
adspub dump -o catalog.json         # full catalog as JSON
adspub cache info                   # where the cache is and how old
adspub cache clear
```

Global options go before the command:

```sh
adspub --json latest                # JSON output, every command supports it
adspub --refresh list               # ignore the cache and fetch now
adspub --offline check v202602      # never touch the network
adspub --max-age 3600 latest        # reuse the cache for at most one hour
```

Example:

```
$ adspub check v202511 v202602 v202608 v202405
deprecated v202511 is deprecated and will be removed; migrate to v202608.
active     v202602 is active but not the latest; v202608 is newer.
active     v202608 is the latest active version.
unlisted   v202405 is not listed and is assumed to be sunset; migrate to v202608.
$ echo $?
20
```

### Caching

Results are cached as a single JSON file for 24 hours by default:

- Linux: `~/.cache/adspub/catalog.json`
- macOS: `~/Library/Caches/adspub/catalog.json`
- Windows: `%LOCALAPPDATA%\adspub\adspub\Cache\catalog.json`

Override the location with `--cache-dir` or the `ADSPUB_CACHE_DIR` environment
variable. If the network is down and a cache exists, the stale cache is used
and a warning is printed to stderr. JSON output always reports where the data
came from (`network`, `cache` or `stale-cache`) and when it was fetched.

### Use in CI

Fail a build when the pinned version is no longer active:

```sh
adspub check "$AD_MANAGER_API_VERSION"
```

Exit code `0` means active, `10` deprecated, `20` unlisted. Use
`|| [ $? -eq 10 ]` if you want deprecated to warn rather than fail.

## AI agent usage

The CLI is designed so an agent can call it without parsing prose:

- `--json` gives structured output on every command.
- Exit codes encode the answer: `0` active, `10` deprecated, `20` unlisted,
  `1` runtime error (network or parse), `2` usage error.
- Output includes a `meta` block with `source` and `fetched_at` so the agent
  can decide whether to re-run with `--refresh`.
- `adspub schema` prints the JSON Schema of the catalog document.
- `adspub parse page.html` parses a saved copy with no network or cache.

Paste this into your agent's instructions file (`CLAUDE.md`, `AGENTS.md`,
a system prompt, or a tool description):

```markdown
## Google Ad Manager API versions

Use the `adspub` CLI (install: `uv tool install adspub`, or run `uvx adspub`)
to find out which Ad Manager API versions are valid. Never guess a version.

- Latest version:          `adspub --json latest`
- Check a pinned version:  `adspub --json check v202602`
- All versions:            `adspub --json list`
- Force a fresh fetch:     add `--refresh` before the command

Exit codes for `check`: 0 active, 10 deprecated, 20 unlisted (assume removed).
Read `.results[].status`, `.results[].latest` and `.results[].newer_versions`
from the JSON. If `.meta.source` is `stale-cache`, retry with `--refresh`.
```

Example JSON from `adspub --json check v202511`:

```json
{
  "ok": false,
  "exit_code": 10,
  "latest": "v202608",
  "results": [
    {
      "version": "v202511",
      "status": "deprecated",
      "is_latest": false,
      "latest": "v202608",
      "newer_versions": ["v202602", "v202605", "v202608"],
      "message": "v202511 is deprecated and will be removed; migrate to v202608."
    }
  ],
  "meta": {
    "source": "cache",
    "fetched_at": "2026-10-09T09:47:14.401329+00:00",
    "cache_age_seconds": 0.7,
    "source_url": "https://ads.google.com/apis/ads/publisher",
    "warning": null
  }
}
```

### As a tool for a Claude agent

A minimal tool definition that wraps the CLI:

```json
{
  "name": "ad_manager_api_version_check",
  "description": "Check whether a Google Ad Manager API version (vYYYYMM) is active, deprecated or unlisted, and get the latest version. Runs `adspub --json check <version>`.",
  "input_schema": {
    "type": "object",
    "properties": {
      "version": { "type": "string", "description": "Version such as v202602" }
    },
    "required": ["version"]
  }
}
```

The tool handler runs `adspub --json check <version>` and returns stdout
verbatim.

## Python API

Everything is async. The CLI is a thin layer over these functions.

```python
import asyncio

from adspub import load_catalog


async def main() -> None:
    result = await load_catalog()  # cache-aware; fetches when stale
    catalog = result.catalog
    print(result.source)  # network | cache | stale-cache
    print(catalog.latest.version)  # v202608
    print([v.version for v in catalog.deprecated])

    check = catalog.check("v202511")
    print(check.status, check.newer_versions, check.message)


asyncio.run(main())
```

Other entry points:

```python
from adspub import fetch_catalog, parse_catalog

catalog = await fetch_catalog()  # no cache
catalog = parse_catalog(html, source_url="https://...")  # from a string
```

`load_catalog` accepts `refresh`, `offline`, `max_age` (seconds), `cache_dir`,
`allow_stale`, `timeout`, and an optional `httpx.AsyncClient` for connection
reuse or testing with `httpx.MockTransport`.

All models are Pydantic v2 (`Catalog`, `ApiVersion`, `Service`,
`VersionCheck`), so `model_dump_json()` and `model_json_schema()` work as
expected.

## Development

```sh
git clone https://github.com/eivl/adspub && cd adspub
uv sync                      # creates .venv with dev dependencies
uv run pre-commit install    # ruff, mypy, uv lock check on commit
uv run pytest                # tests
uv run pytest --cov          # with coverage
uv run ruff check . && uv run ruff format . && uv run mypy
uv run --python 3.11 pytest  # any supported interpreter
```

The demo GIF in this README is rendered from `demo/demo.tape` with
[VHS](https://github.com/charmbracelet/vhs): run `vhs demo/demo.tape` locally, or
trigger the "Render demo" workflow, which commits the updated GIF.

Tests never touch the network. The parser is tested against
`tests/fixtures/publisher.html`, a saved copy of the real page. A weekly GitHub
Actions job parses the live page and warns when the fixture falls behind.

### Releasing

Releases publish to PyPI via GitHub Actions trusted publishing when a `v*` tag
is pushed:

```sh
uv version --bump minor
git commit -am "Release v$(uv version --short)"
git tag "v$(uv version --short)"
git push && git push --tags
```

One-time setup: on PyPI, add a trusted publisher for this repository with
workflow `publish.yml` and environment `pypi`, and create a `pypi` environment
in the GitHub repository settings.

## License

MIT
