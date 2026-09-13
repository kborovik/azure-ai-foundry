# Changelog

## Unreleased

### Changed

- **Unit tests:** drop `talos test` Click command. `gmake test` runs `uv run pytest` (addopts `-m unit`). `gmake check` runs ruff then `test`. GitHub Actions unit workflow runs `uv run pytest`.
- **Generate group:** `uv run talos generate` is a Click group (`policy`, `application`). Bare `talos generate` prints help and exits 2. `talos generate policy` is the existing policy render and does not run deploy.
- **Standing terraform init:** `gmake infra-init` and README use `-reconfigure`, not `-migrate-state`. Remote azurerm state is already live. Reconstruct after clone with backend-config `key=<env>.tfstate`.
- **Storage network:** `azurerm_storage_account` uses `public_network_access = "Enabled"` (string). Deprecated `public_network_access_enabled` is dropped on storage. Search and Foundry keep the bool attribute. AzureRM provider floor is `>= 5.5.0`.
- **Env fill:** `gmake infra-create` writes `infra/outputs.json` (`terraform output -json` shape). Talos and pytest fill missing canonical env from that file unless `--no-terraform`. They never spawn `terraform output`. `gmake infra-destroy` drops the file. The file is gitignored.
- **Infra backend:** `gmake infra-backend-create` / `infra-backend-show` / `infra-backend-destroy` use Azure CLI (`az group create`, `az storage account create`, `az storage container create`, `az group show` / `az storage account show`, `az group delete`). Drop `infra/backend/` Terraform. Account name is the fixed string `sttfstlab5` (never workload `stcp*`). Operator gets Storage Blob Data Contributor on the account.
- **Make recipes:** Rename `gmake infra` to `gmake infra-create` and `gmake infra-backend` to `gmake infra-backend-create`. Add `gmake infra-show` (`terraform show`) and `gmake infra-backend-show` (`az show`).
- **Infra:** Remote azurerm state (Azure AD) in `rg-credit-policy-tfstate`. Apply uses `infra/dev1.tfvars` or `infra/prd1.tfvars`. Environment names are `dev1` and `prd1` only (`credit-policy-demo` dropped). `gmake infra-create` defaults to `ENV=dev1`. GitHub release init uses backend key `prd1.tfstate`.
- **Infra:** Swap `azd` + Bicep for Terraform CLI in `infra/`. Drop `azure.yaml`. `gmake infra-create` runs `terraform apply`. State files are gitignored.
- **Env load:** Talos and pytest no longer read repo-root `.env`. Missing keys come from process env, then `infra/outputs.json` unless `--no-terraform`. `.env.example` is removed. `.gitignore` still lists `.env`.
- **CI:** Bump GitHub Actions to Node.js 24 runtimes (`actions/checkout@v7`, `astral-sh/setup-uv` v10.1.0, `azure/login@v3`) so runners stop forcing Node 20. Release deploy uses Terraform, not `azd`.

### Added

- **`talos publish`:** optional REST path for Teams Just you (`publishScope=Shared`, `BotServiceRbac`). Creates the Azure Bot Service + Teams channel, merge-patches Activity without dropping existing `protocol_configuration` / `authorization_schemes`, then POSTs Foundry's Microsoft 365 publish API. `--dry-run` prints the plan. Portal Direct publish remains valid. Hosted-agent spike: [docs/hosted-agents.md](docs/hosted-agents.md).
- **EvaluationMode:** `agents/credit-policy-agent.instructions.md` evaluates by `application_id` or `customer_name`, asks if both are missing, and cites policy documents only.
- **Teams Just-you:** runbook in `docs/teams.md` (BotServiceRbac, sideload fallback, evaluate-by-id and evaluate-by-name). Marker `teams` skips unless `E2E_TEAMS=1`; flag set with no Activity client skips, not fails.
- **Live pytest:** markers `ingestion`, `retrieval`, and `agent` skip without canonical Azure env. Evaluate-by-id, evaluate-by-name, ask-when-missing, and one case per ApplicationType. Unit fixtures in `tests/fixtures/client-applications/`.
- **`talos deploy` two sources:** blob-sync both local corpora (hash-skip), PUT `ks-credit-policies` and `ks-client-applications`, run both indexers, `--wait` until policy ≥12 and application ≥3, PUT `kb-credit-policies` with both sources, ARM MCP connection, agent version pin. Omit stored `temperature` for `gpt-5*` (invoke 400s otherwise); set `temperature=0` on other models. `gmake deploy` and release CI generate the three application slots before `--wait`. Blob container `client-applications` is in Terraform.
- **`talos generate application`:** Foundry `gpt-5-mini` emits a unique SyntheticBorrower (`--type` or `--all`; `--force` overwrites a slot). Validate+one retry. Gitignore `data/client-applications/*.md` and `manifest.json`. Optional blob hash-skip. Does not PUT knowledge sources.
- **`gmake infra-plan`:** `terraform plan` in `infra/` with `-var-file=<env>.tfvars` after `infra-init` (`ENV=dev1|prd1`). Does not write `infra/outputs.json`.
- **`gmake infra-backend-create` / `infra-backend-show` / `infra-backend-destroy` / `infra-destroy`:** bootstrap the tfstate account via Azure CLI (fixed name `sttfstlab5`, never workload `stcp*`); show or destroy the workload stack or the backend resource group. Standing workload `terraform init` uses `-reconfigure`.
- **`gmake infra-create` / `infra-show`:** check `az` auth, `terraform -chdir=infra init`, then `terraform apply` or `terraform show` with `location=swedencentral`.
- **Blob dual-write:** `uv run talos generate` uploads the 12 Markdown policies to container `credit-policies`. Skip uses blob metadata `content_sha256` (not Content-MD5). Auth is `AZURE_STORAGE_CONNECTION_STRING` if set, else `DefaultAzureCredential` + `AZURE_STORAGE_ACCOUNT_URL`.
- **Infra:** Terraform provisions Storage, Azure AI Search Basic, a Foundry project with system-assigned MI, `gpt-5-mini` GlobalStandard (capacity 50), `text-embedding-3-large`, and RBAC. Default location `swedencentral`. Canonical outputs only.
- **Talos CLI:** Click package `talos` (`uv run talos generate` / `talos deploy` / `talos publish`) renders the synthetic corpus and provisions Foundry IQ. Unit tests run via `gmake test` → `uv run pytest`. GitHub Actions deploy runs on `release: published`.
- **Corpus generator:** `uv run talos generate --local-only` writes 12 watermarked Markdown policies plus `manifest.json` from `corpus/facts.yaml`.
- **`gmake` recipes:** local `test`, `check`, `generate`, `deploy`, `e2e`, and `gmake release major|minor|patch` (bump, tag, `gh release create`).
