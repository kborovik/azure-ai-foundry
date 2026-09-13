# Changelog

## Unreleased

### Changed

- **Infra:** Swap `azd` + Bicep for Terraform CLI in `infra/`. Drop `azure.yaml`. `gmake infra` runs `terraform apply`. Canonical outputs fill missing env via `terraform -chdir=infra output -json` unless `--no-terraform`. State files are gitignored.
- **Env load:** Talos and pytest no longer read repo-root `.env`. Missing keys come from process env, then Terraform output unless `--no-terraform`. `.env.example` is removed. `.gitignore` still lists `.env`.
- **CI:** Bump GitHub Actions to Node.js 24 runtimes (`actions/checkout@v7`, `astral-sh/setup-uv` v10.1.0, `azure/login@v3`) so runners stop forcing Node 20. Release deploy uses Terraform, not `azd`.

### Added

- **`gmake infra`:** check `az` auth, `terraform -chdir=infra init`, then `terraform apply` with `location=swedencentral`.
- **Blob dual-write:** `uv run talos generate` uploads the 12 Markdown policies to container `credit-policies`. Skip uses blob metadata `content_sha256` (not Content-MD5). Auth is `AZURE_STORAGE_CONNECTION_STRING` if set, else `DefaultAzureCredential` + `AZURE_STORAGE_ACCOUNT_URL`.
- **Infra:** Terraform provisions Storage, Azure AI Search Basic, a Foundry project with system-assigned MI, `gpt-5-mini` GlobalStandard (capacity 50), `text-embedding-3-large`, and RBAC. Default location `swedencentral`. Canonical outputs only.
- **Talos CLI:** Click package `talos` (`uv run talos generate` / `talos deploy` / `talos test`) renders the synthetic corpus, provisions Foundry IQ, and runs pytest. GitHub Actions deploy runs on `release: published`.
- **Corpus generator:** `uv run talos generate --local-only` writes 12 watermarked Markdown policies plus `manifest.json` from `corpus/facts.yaml`.
- **`gmake` recipes:** local `check`, `generate`, `deploy`, `e2e`, and `gmake release major|minor|patch` (bump, tag, `gh release create`).
