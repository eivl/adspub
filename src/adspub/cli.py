"""Typer command line interface.

Every command accepts ``--json`` for machine-readable output. Exit codes are
stable so scripts and AI agents can branch on them without parsing text:

* ``0``  success (for ``check``: every version is active)
* ``10`` ``check``: at least one version is deprecated
* ``20`` ``check``: at least one version is not listed (assumed sunset)
* ``1``  runtime error such as a network or parse failure
* ``2``  usage error (unknown option, bad argument)
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel, ConfigDict
from rich.console import Console
from rich.table import Table

from adspub import __version__
from adspub.cache import cache_age, cache_path, clear_cache, read_cache
from adspub.catalog import DEFAULT_MAX_AGE, LoadResult, Source, load_catalog
from adspub.fetch import DEFAULT_URL, FetchError
from adspub.models import ApiVersion, Catalog, VersionCheck, VersionStatus, normalize_version
from adspub.parser import ParseError, parse_catalog

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_DEPRECATED = 10
EXIT_UNLISTED = 20

_STATUS_EXIT = {
    VersionStatus.ACTIVE: EXIT_OK,
    VersionStatus.DEPRECATED: EXIT_DEPRECATED,
    VersionStatus.UNLISTED: EXIT_UNLISTED,
}
_STATUS_STYLE = {
    VersionStatus.ACTIVE: "green",
    VersionStatus.DEPRECATED: "yellow",
    VersionStatus.UNLISTED: "red",
}

app = typer.Typer(
    name="adspub",
    help="Machine-readable view of the Google Ad Manager API version list.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)
cache_app = typer.Typer(help="Inspect or clear the local cache.", no_args_is_help=True)
app.add_typer(cache_app, name="cache")

stdout = Console(soft_wrap=True)
stderr = Console(stderr=True, soft_wrap=True)


@dataclass
class Options:
    """Global options shared by every command."""

    json: bool
    refresh: bool
    offline: bool
    max_age: float
    url: str
    cache_dir: Path | None


class Meta(BaseModel):
    """Provenance block attached to JSON output."""

    model_config = ConfigDict(frozen=True)

    source: Source
    fetched_at: str
    cache_age_seconds: float
    source_url: str
    warning: str | None = None


def _meta(result: LoadResult) -> Meta:
    return Meta(
        source=result.source,
        fetched_at=result.catalog.fetched_at.isoformat(),
        cache_age_seconds=round(result.cache_age_seconds, 1),
        source_url=result.catalog.source_url,
        warning=result.warning,
    )


def _emit_json(payload: Any) -> None:
    if isinstance(payload, BaseModel):
        text = payload.model_dump_json(indent=2)
    else:
        text = json.dumps(payload, indent=2, default=_json_default)
    print(text)


def _json_default(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    msg = f"not JSON serialisable: {type(value).__name__}"
    raise TypeError(msg)


def _fail(message: str) -> typer.Exit:
    stderr.print(f"[red]error:[/red] {message}")
    return typer.Exit(EXIT_ERROR)


def _load(opts: Options) -> LoadResult:
    try:
        return asyncio.run(
            load_catalog(
                url=opts.url,
                refresh=opts.refresh,
                offline=opts.offline,
                max_age=opts.max_age,
                cache_dir=opts.cache_dir,
            )
        )
    except (FetchError, ParseError) as exc:
        raise _fail(str(exc)) from exc


def _version_callback(value: bool) -> None:
    if value:
        print(f"adspub {__version__}")
        raise typer.Exit


@app.callback()
def main(
    ctx: typer.Context,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit JSON instead of human-readable text.")
    ] = False,
    refresh: Annotated[
        bool, typer.Option("--refresh", help="Ignore the cache and fetch the page again.")
    ] = False,
    offline: Annotated[
        bool, typer.Option("--offline", help="Never touch the network; use the cache only.")
    ] = False,
    max_age: Annotated[
        float,
        typer.Option(
            "--max-age",
            min=0,
            help="Reuse the cache while it is younger than this many seconds.",
            show_default=True,
        ),
    ] = DEFAULT_MAX_AGE,
    url: Annotated[
        str, typer.Option("--url", envvar="ADSPUB_URL", help="Page to fetch.")
    ] = DEFAULT_URL,
    cache_dir: Annotated[
        Path | None,
        typer.Option(
            "--cache-dir",
            envvar="ADSPUB_CACHE_DIR",
            help="Directory for the cache file.",
            show_default="platform user cache dir",
        ),
    ] = None,
    _version: Annotated[
        bool,
        typer.Option(
            "--version", "-V", callback=_version_callback, is_eager=True, help="Show version."
        ),
    ] = False,
) -> None:
    """Machine-readable view of the Google Ad Manager API version list."""
    if refresh and offline:
        stderr.print("[red]error:[/red] --refresh and --offline cannot be combined")
        raise typer.Exit(2)
    ctx.obj = Options(
        json=json_output,
        refresh=refresh,
        offline=offline,
        max_age=max_age,
        url=url,
        cache_dir=cache_dir,
    )


def _opts(ctx: typer.Context) -> Options:
    obj = ctx.obj
    if not isinstance(obj, Options):  # pragma: no cover - defensive
        msg = "global options not initialised"
        raise RuntimeError(msg)
    return obj


# -- commands --------------------------------------------------------------


@app.command()
def latest(ctx: typer.Context) -> None:
    """Print the latest active API version."""
    opts = _opts(ctx)
    result = _load(opts)
    try:
        version = result.catalog.latest
    except LookupError as exc:
        raise _fail(str(exc)) from exc
    if opts.json:
        _emit_json(
            {
                "version": version.version,
                "status": version.status,
                "service_count": len(version.services),
                "meta": _meta(result),
            }
        )
    else:
        print(version.version)


@app.command(name="list")
def list_versions(
    ctx: typer.Context,
    active_only: Annotated[bool, typer.Option("--active", help="Only active versions.")] = False,
    deprecated_only: Annotated[
        bool, typer.Option("--deprecated", help="Only deprecated versions.")
    ] = False,
) -> None:
    """List every version on the page with its status."""
    opts = _opts(ctx)
    result = _load(opts)
    catalog = result.catalog
    versions: list[ApiVersion] = catalog.versions
    if active_only:
        versions = catalog.active
    elif deprecated_only:
        versions = catalog.deprecated

    latest_version = catalog.latest.version if catalog.active else None
    if opts.json:
        _emit_json(
            {
                "latest": latest_version,
                "versions": [
                    {
                        "version": v.version,
                        "status": v.status,
                        "is_latest": v.version == latest_version,
                        "service_count": len(v.services),
                    }
                    for v in versions
                ],
                "meta": _meta(result),
            }
        )
        return

    table = Table(title=catalog.title or "Ad Manager API versions")
    table.add_column("Version")
    table.add_column("Status")
    table.add_column("Services", justify="right")
    for v in versions:
        label = v.status + (" (latest)" if v.version == latest_version else "")
        table.add_row(
            v.version, f"[{_STATUS_STYLE[VersionStatus(v.status)]}]{label}[/]", str(len(v.services))
        )
    stdout.print(table)
    _print_source_line(result)


@app.command()
def check(
    ctx: typer.Context,
    versions: Annotated[
        list[str],
        typer.Argument(help="One or more versions, for example v202602.", metavar="VERSION..."),
    ],
) -> None:
    """Check whether versions are active, deprecated or unlisted.

    Exit code: 0 all active, 10 any deprecated, 20 any unlisted.
    """
    opts = _opts(ctx)
    canonical: list[str] = []
    for raw in versions:
        try:
            canonical.append(normalize_version(raw))
        except ValueError as exc:
            stderr.print(f"[red]error:[/red] {exc}")
            raise typer.Exit(2) from exc

    result = _load(opts)
    checks: list[VersionCheck] = [result.catalog.check(v) for v in canonical]
    exit_code = max(_STATUS_EXIT[c.status] for c in checks)

    if opts.json:
        _emit_json(
            {
                "ok": exit_code == EXIT_OK,
                "exit_code": exit_code,
                "latest": result.catalog.latest.version,
                "results": checks,
                "meta": _meta(result),
            }
        )
    else:
        for c in checks:
            stdout.print(f"[{_STATUS_STYLE[c.status]}]{c.status:<10}[/] {c.message}")
        _print_source_line(result)
    raise typer.Exit(exit_code)


@app.command()
def services(
    ctx: typer.Context,
    version: Annotated[str, typer.Argument(help="Version, for example v202602.")],
) -> None:
    """List the SOAP services available in a version."""
    opts = _opts(ctx)
    try:
        canonical = normalize_version(version)
    except ValueError as exc:
        stderr.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(2) from exc
    result = _load(opts)
    found = result.catalog.get(canonical)
    if found is None:
        raise _fail(f"{canonical} is not listed on the page")

    if opts.json:
        _emit_json({"version": found, "meta": _meta(result)})
        return

    table = Table(title=f"{found.version} ({found.status})")
    table.add_column("Service")
    table.add_column("WSDL")
    table.add_column("Docs")
    for s in found.services:
        table.add_row(s.name, s.wsdl_url, s.docs_url or "")
    stdout.print(table)
    _print_source_line(result)


@app.command()
def dump(
    ctx: typer.Context,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write to this file instead of stdout.")
    ] = None,
) -> None:
    """Write the full catalog as JSON."""
    opts = _opts(ctx)
    result = _load(opts)
    text = result.catalog.model_dump_json(indent=2)
    if output is None:
        print(text)
    else:
        output.write_text(text + "\n", encoding="utf-8")
        if not opts.json:
            stderr.print(f"wrote {output}")


@app.command()
def parse(
    ctx: typer.Context,
    file: Annotated[
        Path, typer.Argument(help="HTML file to parse, or - for stdin.", allow_dash=True)
    ],
    source_url: Annotated[
        str, typer.Option("--source-url", help="URL recorded in the output and used for links.")
    ] = DEFAULT_URL,
) -> None:
    """Parse a local copy of the page into catalog JSON (no network, no cache)."""
    _opts(ctx)
    html = sys.stdin.read() if str(file) == "-" else file.read_text(encoding="utf-8")
    try:
        catalog = parse_catalog(html, source_url=source_url)
    except ParseError as exc:
        raise _fail(str(exc)) from exc
    print(catalog.model_dump_json(indent=2))


@app.command()
def schema(ctx: typer.Context) -> None:
    """Print the JSON Schema of the catalog document."""
    _opts(ctx)
    _emit_json(Catalog.model_json_schema())


# -- cache -----------------------------------------------------------------


@cache_app.command(name="path")
def cache_path_cmd(ctx: typer.Context) -> None:
    """Print the cache file path."""
    opts = _opts(ctx)
    path = cache_path(opts.cache_dir)
    if opts.json:
        _emit_json({"path": str(path), "exists": path.exists()})
    else:
        print(path)


@cache_app.command(name="info")
def cache_info(ctx: typer.Context) -> None:
    """Show cache location, age and contents summary."""
    opts = _opts(ctx)
    path = cache_path(opts.cache_dir)
    cached = asyncio.run(read_cache(opts.cache_dir))
    if cached is None:
        if opts.json:
            _emit_json({"path": str(path), "exists": False})
        else:
            print(f"{path}: no cache")
        return
    age = cache_age(cached)
    if opts.json:
        _emit_json(
            {
                "path": str(path),
                "exists": True,
                "fetched_at": cached.fetched_at.isoformat(),
                "age_seconds": round(age, 1),
                "fresh": age <= opts.max_age,
                "versions": [v.version for v in cached.versions],
            }
        )
    else:
        state = "fresh" if age <= opts.max_age else "stale"
        print(f"{path}")
        print(f"fetched {cached.fetched_at.isoformat()} ({age:.0f}s ago, {state})")
        print("versions: " + ", ".join(v.version for v in cached.versions))


@cache_app.command(name="clear")
def cache_clear(ctx: typer.Context) -> None:
    """Delete the cache file."""
    opts = _opts(ctx)
    removed = asyncio.run(clear_cache(opts.cache_dir))
    if opts.json:
        _emit_json({"path": str(cache_path(opts.cache_dir)), "removed": removed})
    else:
        print("cache cleared" if removed else "no cache to clear")


def _print_source_line(result: LoadResult) -> None:
    age = result.cache_age_seconds
    detail = {
        Source.NETWORK: "fetched just now",
        Source.CACHE: f"from cache, {age:.0f}s old",
        Source.STALE_CACHE: f"from STALE cache, {age:.0f}s old (network failed)",
    }[result.source]
    stderr.print(f"[dim]{detail}[/dim]")


if __name__ == "__main__":  # pragma: no cover
    app()
