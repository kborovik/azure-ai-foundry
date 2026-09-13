# Changelog

## Unreleased

### Changed

- **Storage network:** `azurerm_storage_account` uses `public_network_access = "Enabled"` (string). Deprecated `public_network_access_enabled` is dropped on storage. Search and Foundry keep the bool attribute. AzureRM provider floor is `>= 5.5.0`.
- **Env fill:** `gmake infra-create` writes `infra/outputs.json` (`terraform output -json` shape). Talos and pytest fill missing canonical env from that file unless `--no-terraform`. They never spawn `terraform output`. `gmake infra-destroy` drops the file. The file is gitignored.
- **Infra backend:** `gmake infra-backend-create` / `infra-backend-show` / `infra-backend-destroy` use Azure CLI (`az group create`, `az storage account create`, `az storage container create`, `az group show` / `az storage account show`, `az group delete`). Drop `infra/backend/` Terraform. Account name is the fixed string `sttfstlab5` (never workload `stcp*`). Operator gets Storage Blob Data Contributor on the account.
- **Make recipes:** Rename `gmake infra` to `gmake infra-create` and `gmake infra-backend` to `gmake infra-backend-create`. Add `gmake infra-show` (`terraform show`) and `gmake infra-backend-show` (`az show`).
- **Infra:** Remote azurerm state (Azure AD) in `rg-credit-policy-tfstate`. Apply uses `infra/dev1.tfvars` or `infra/prd1.tfvars`. Environment names are `dev1` and `prd1` only (`credit-policy-demo` dropped). `gmake infra-create` defaults to `ENV=dev1`. GitHub release init uses backend key `prd1.tfstate`.
- **Infra:** Swap `azd` + Bicep for Terraform CLI in `infra/`. Drop `azure.yaml`. `gmake infra-create` runs `terraform apply`. State files are gitignored.
- **Env load:** Talos and pytest no longer read repo-root `.env`. Missing keys come from process env, then `infra/outputs.json` unless `--no-terraform`. `.env.example` is removed. `.gitignore` still lists `.env`.
- **CI:** Bump GitHub Actions to Node.js 24 runtimes (`actions/checkout@v7`, `astral-sh/setup-uv` v10.1.0, `azure/login@v3`) so runners stop forcing Node 20. Release deploy uses Terraform, not `azd`.

### Added

- **`gmake infra-backend-create` / `infra-backend-show` / `infra-backend-destroy` / `infra-destroy`:** bootstrap the tfstate account via Azure CLI (fixed name `sttfstlab5`, never workload `stcp*`); show or destroy the workload stack or the backend resource group. First workload `terraform init` uses `-migrate-state` when a local `infra/terraform.tfstate` exists.
- **`gmake infra-create` / `infra-show`:** check `az` auth, `terraform -chdir=infra init`, then `terraform apply` or `terraform show` with `location=swedencentral`.
- **Blob dual-write:** `uv run talos generate` uploads the 12 Markdown policies to container `credit-policies`. Skip uses blob metadata `content_sha256` (not Content-MD5). Auth is `AZURE_STORAGE_CONNECTION_STRING` if set, else `DefaultAzureCredential` + `AZURE_STORAGE_ACCOUNT_URL`.
- **Infra:** Terraform provisions Storage, Azure AI Search Basic, a Foundry project with system-assigned MI, `gpt-5-mini` GlobalStandard (capacity 50), `text-embedding-3-large`, and RBAC. Default location `swedencentral`. Canonical outputs only.
- **Talos CLI:** Click package `talos` (`uv run talos generate` / `talos deploy` / `talos test`) renders the synthetic corpus, provisions Foundry IQ, and runs pytest. GitHub Actions deploy runs on `release: published`.
- **Corpus generator:** `uv run talos generate --local-only` writes 12 watermarked Markdown policies plus `manifest.json` from `corpus/facts.yaml`.
- **`gmake` recipes:** local `check`, `generate`, `deploy`, `e2e`, and `gmake release major|minor|patch` (bump, tag, `gh release create`).
