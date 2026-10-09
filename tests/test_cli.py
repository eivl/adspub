from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from adspub import __version__
from adspub.cache import write_cache
from adspub.cli import EXIT_DEPRECATED, EXIT_ERROR, EXIT_OK, EXIT_UNLISTED, app
from adspub.models import Catalog

runner = CliRunner()


@pytest.fixture
def cached(cache_dir: Path, catalog: Catalog) -> Catalog:
    """A fresh cache so commands never hit the network."""
    recent = catalog.model_copy(update={"fetched_at": datetime.now(UTC)})
    asyncio.run(write_cache(recent))
    return recent


def run(*args: str) -> Result:
    return runner.invoke(app, list(args))


def test_version_flag() -> None:
    result = run("--version")
    assert result.exit_code == 0
    assert __version__ in result.output


def test_help_lists_commands() -> None:
    result = run("--help")
    assert result.exit_code == 0
    for name in ("latest", "list", "check", "services", "dump", "parse", "schema", "cache"):
        assert name in result.output


def test_latest_text(cached: Catalog) -> None:
    result = run("--offline", "latest")
    assert result.exit_code == EXIT_OK
    assert result.stdout.strip() == "v202608"


def test_latest_json(cached: Catalog) -> None:
    result = run("--json", "--offline", "latest")
    assert result.exit_code == EXIT_OK
    data = json.loads(result.stdout)
    assert data["version"] == "v202608"
    assert data["status"] == "active"
    assert data["meta"]["source"] == "cache"


def test_list_json(cached: Catalog) -> None:
    result = run("--json", "--offline", "list")
    data = json.loads(result.stdout)
    assert data["latest"] == "v202608"
    assert [v["version"] for v in data["versions"]] == ["v202511", "v202602", "v202605", "v202608"]
    assert data["versions"][0]["status"] == "deprecated"
    assert data["versions"][-1]["is_latest"] is True


def test_list_filters(cached: Catalog) -> None:
    active = json.loads(run("--json", "--offline", "list", "--active").stdout)
    assert [v["version"] for v in active["versions"]] == ["v202602", "v202605", "v202608"]
    deprecated = json.loads(run("--json", "--offline", "list", "--deprecated").stdout)
    assert [v["version"] for v in deprecated["versions"]] == ["v202511"]


def test_list_text(cached: Catalog) -> None:
    result = run("--offline", "list")
    assert result.exit_code == EXIT_OK
    assert "v202608" in result.stdout
    assert "latest" in result.stdout


@pytest.mark.parametrize(
    ("version", "code"),
    [
        ("v202608", EXIT_OK),
        ("v202602", EXIT_OK),
        ("v202511", EXIT_DEPRECATED),
        ("v202405", EXIT_UNLISTED),
    ],
)
def test_check_exit_codes(cached: Catalog, version: str, code: int) -> None:
    result = run("--offline", "check", version)
    assert result.exit_code == code


def test_check_worst_status_wins(cached: Catalog) -> None:
    result = run("--json", "--offline", "check", "v202608", "v202511", "v202405")
    assert result.exit_code == EXIT_UNLISTED
    data = json.loads(result.stdout)
    assert data["ok"] is False
    assert data["exit_code"] == EXIT_UNLISTED
    assert [r["status"] for r in data["results"]] == ["active", "deprecated", "unlisted"]
    assert data["results"][1]["newer_versions"] == ["v202602", "v202605", "v202608"]


def test_check_ok_json(cached: Catalog) -> None:
    data = json.loads(run("--json", "--offline", "check", "202608").stdout)
    assert data["ok"] is True
    assert data["results"][0]["is_latest"] is True


def test_check_invalid_version_is_usage_error(cached: Catalog) -> None:
    result = run("--offline", "check", "banana")
    assert result.exit_code == 2
    assert "invalid" in result.output


def test_services(cached: Catalog) -> None:
    data = json.loads(run("--json", "--offline", "services", "v202608").stdout)
    names = [s["name"] for s in data["version"]["services"]]
    assert "LineItemService" in names
    text = run("--offline", "services", "v202608")
    assert "LineItemService" in text.stdout


def test_services_unlisted(cached: Catalog) -> None:
    result = run("--offline", "services", "v202405")
    assert result.exit_code == EXIT_ERROR
    assert "not listed" in result.output


def test_dump_stdout_and_file(cached: Catalog, tmp_path: Path) -> None:
    result = run("--offline", "dump")
    assert result.exit_code == EXIT_OK
    assert Catalog.model_validate_json(result.stdout) == cached

    target = tmp_path / "out.json"
    result = run("--offline", "dump", "-o", str(target))
    assert result.exit_code == EXIT_OK
    assert Catalog.model_validate_json(target.read_text()) == cached


def test_parse_file_and_stdin(page_html: str, tmp_path: Path) -> None:
    source = tmp_path / "page.html"
    source.write_text(page_html, encoding="utf-8")
    result = run("parse", str(source))
    assert result.exit_code == EXIT_OK
    assert Catalog.model_validate_json(result.stdout).latest.version == "v202608"

    result = runner.invoke(app, ["parse", "-"], input=page_html)
    assert result.exit_code == EXIT_OK
    assert "v202608" in result.stdout


def test_parse_bad_page(tmp_path: Path) -> None:
    source = tmp_path / "page.html"
    source.write_text("<html></html>")
    result = run("parse", str(source))
    assert result.exit_code == EXIT_ERROR


def test_schema() -> None:
    result = run("schema")
    assert result.exit_code == EXIT_OK
    schema = json.loads(result.stdout)
    assert schema["title"] == "Catalog"
    assert "versions" in schema["properties"]


def test_offline_without_cache(cache_dir: Path) -> None:
    result = run("--offline", "latest")
    assert result.exit_code == EXIT_ERROR
    assert "offline" in result.output


def test_refresh_and_offline_conflict() -> None:
    result = run("--refresh", "--offline", "latest")
    assert result.exit_code == 2


def test_cache_commands(cache_dir: Path, cached: Catalog) -> None:
    path = run("cache", "path").stdout.strip()
    assert path == str(cache_dir / "catalog.json")

    info = json.loads(run("--json", "cache", "info").stdout)
    assert info["exists"] is True
    assert info["fresh"] is True
    assert info["versions"][-1] == "v202608"

    text = run("cache", "info").stdout
    assert "fresh" in text

    cleared = json.loads(run("--json", "cache", "clear").stdout)
    assert cleared["removed"] is True
    assert run("cache", "clear").stdout.strip() == "no cache to clear"
    assert run("cache", "info").stdout.strip().endswith("no cache")
    assert json.loads(run("--json", "cache", "info").stdout)["exists"] is False


def test_cache_info_stale(cache_dir: Path, catalog: Catalog) -> None:
    old = catalog.model_copy(update={"fetched_at": datetime.now(UTC) - timedelta(days=3)})
    asyncio.run(write_cache(old))
    info = json.loads(run("--json", "cache", "info").stdout)
    assert info["fresh"] is False
    assert "stale" in run("cache", "info").stdout


def test_check_without_active_versions(cache_dir: Path, catalog: Catalog) -> None:
    only_deprecated = catalog.model_copy(
        update={"fetched_at": datetime.now(UTC), "versions": catalog.deprecated}
    )
    asyncio.run(write_cache(only_deprecated))
    result = run("--offline", "check", "v202511")
    assert result.exit_code == EXIT_ERROR
    assert "no active versions" in result.output
