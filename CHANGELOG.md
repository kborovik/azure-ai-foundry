# Changelog

## Unreleased

### Changed

- **CI:** Bump GitHub Actions to Node.js 24 runtimes (`actions/checkout@v7`, `astral-sh/setup-uv` v10.1.0, `azure/login@v3`) so runners stop forcing Node 20.

### Added

- **Talos CLI:** Click package `talos` (`uv run talos deploy` / `talos test`) provisions Foundry IQ and runs pytest. GitHub Actions deploy runs on `release: published`.
- **`gmake` recipes:** local `check`, `generate`, `deploy`, `e2e`, and `gmake release major|minor|patch` (bump, tag, `gh release create`).
