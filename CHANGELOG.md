# Changelog

## Unreleased

### Changed

- **CI:** Bump GitHub Actions to Node.js 24 runtimes (`actions/checkout@v7`, `astral-sh/setup-uv` v10.1.0, `azure/login@v3`) so runners stop forcing Node 20.

### Added

- **Infra:** `azd` + Bicep (`azure.yaml` module `main`) provision Storage, Azure AI Search Basic, a Foundry project with system-assigned MI, `gpt-5-mini` GlobalStandard (capacity 50), `text-embedding-3-large`, and RBAC. Default location `swedencentral`. Canonical outputs only.
- **Talos CLI:** Click package `talos` (`uv run talos generate` / `talos deploy` / `talos test`) renders the synthetic corpus, provisions Foundry IQ, and runs pytest. GitHub Actions deploy runs on `release: published`.
- **Corpus generator:** `uv run talos generate --local-only` writes 12 watermarked Markdown policies plus `manifest.json` from `corpus/facts.yaml`.
- **`gmake` recipes:** local `check`, `generate`, `deploy`, `e2e`, and `gmake release major|minor|patch` (bump, tag, `gh release create`).
