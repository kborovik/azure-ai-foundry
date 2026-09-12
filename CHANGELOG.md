# Changelog

## Unreleased

### Added

- **Talos CLI:** Click package `talos` (`uv run talos deploy` / `talos test`) provisions Foundry IQ and runs pytest. GitHub Actions deploy runs on `release: published`.
- **`gmake` recipes:** local `check`, `generate`, `deploy`, `e2e`, and `gmake release major|minor|patch` (bump, tag, `gh release create`).
