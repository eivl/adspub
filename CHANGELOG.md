# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.1] - 2026-10-09

### Changed

- Release pipeline now publishes through PyPI trusted publishing.
- GitHub Actions dependencies updated (checkout v7, upload-artifact v6, download-artifact v7,
  action-gh-release v3, git-auto-commit-action v7).

### Fixed

- Cache directory test on Windows.
- README code blocks are formatted by ruff.

## [0.1.0] - 2026-10-09

### Added

- Parser for <https://ads.google.com/apis/ads/publisher> into a typed catalog.
- Async Python API: `load_catalog`, `fetch_catalog`, `parse_catalog`.
- CLI: `latest`, `list`, `check`, `services`, `dump`, `parse`, `schema`, `cache`.
- Local JSON cache with configurable max age, offline mode and stale fallback.
- Stable exit codes for agent use: 0 active, 10 deprecated, 20 unlisted, 1 error.
