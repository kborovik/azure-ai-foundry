# SPEC — Bank Credit Policy Agent Demo

## §G GOAL

Demo Foundry prompt agent (1) answers credit-policy questions from 12 synthetic Markdown docs in Foundry IQ w/ citations (2) evaluates 3 local synthetic client applications (`accepted`|`rejected`|`missing-data`) in Microsoft Teams 1:1 by `application_id` or `customer_name`, judgement grounded in named policy docs — not a production credit system.

## §C CONSTRAINTS

- demo: synthetic evaluation only; no origination system-of-record; no real borrower PII; no real bank IP; no production credit decisioning; no document ACLs / Purview
- thin stack: Foundry Agent Service prompt agent + Foundry IQ + portal/REST Teams publish; hosted agents + Microsoft 365 Agents SDK = alternative not v1
- Markdown-only corpus v1; no PDF
- no multi-agent, no write-back to core banking
- public network access on; no Private Link / CMK
- KB returns extractive chunks; agent LLM synthesizes; no KB `answerSynthesis`
- Search SKU Basic (MI required); semantic-ranker concurrency 2 per SU → serialize demo chats
- Search REST `2026-08-01-preview` (preview risk); pin client `azure-search-documents==12.1.0b2`
- CPython 3.14; `requires-python = ">=3.14"`; `[tool.uv] python-preference = "managed"`; no PEP 723 scripts
- one CLI `talos` (generate, deploy); unit via `gmake test` → `uv run pytest`; GitHub Actions unit `uv run pytest`; generate/deploy still `uv run talos`
- default region `swedencentral`; never new Search in eastus/eastus2/westus/westus3; never westus2 (no GlobalStandard `gpt-5-mini`)
- local auth keys allowed on resource; never committed; do not set `disableLocalAuth: true`
- no Application Insights in v1 Terraform; no azd
- default CI = unit corpus/CLI tests; live Azure behind pytest markers; Teams opt-in `E2E_TEAMS=1`

## §I INTERFACES

- cmd: `uv run talos generate` Click group; bare → help exit 2. `uv run talos generate policy` → render facts+templates, write `data/credit-policies/`, optional blob upload; `--local-only` / `--azure-only` mutex; `--dry-run` / `--force` / `--fail-if-missing-azure` / `--no-terraform`; exit 0 ok, 1 render/upload, 2 Azure missing, 3 facts invalid; ! indexer; ! deploy. `uv run talos generate application` → Foundry `gpt-5-mini` unique SyntheticBorrower; `--type accepted|rejected|missing-data` or `--all`; `--force` overwrite slot; `--local-only` skip blob; `--dry-run` ! LLM; exit 1 LLM/write, 2 Azure missing; gitignore `data/client-applications/*.md` + `manifest.json`; ! KS PUT. `uv run talos deploy` → blob-sync both corpora hash-skip, PUT `ks-credit-policies` + `ks-client-applications`, POST both generated indexers, poll `--wait` both, KB PUT both sources, ARM MCP connection, agent `create_version` omit stored temperature on `gpt-5*` (invoke 400); temperature=0 on other models; merge-patch `version_selector`; `--skip-indexer-run` / `--skip-endpoint-patch` / `--dry-run` / `--no-terraform`. `uv run talos publish` → optional Teams Just you REST (`publishScope=Shared`, `BotServiceRbac`); PUT Azure Bot + MsTeamsChannel; merge-patch Activity + BotServiceRbac keep existing `protocol_configuration`/`authorization_schemes`; POST `/agents/<name>/microsoft365/publish`; `--dry-run` / `--skip-endpoint-patch` / `--bot-arm-id` / `--app-version` / `--no-terraform`; exit 0 ok, 1 publish/bot, 2 Azure missing; portal Direct publish still valid. Missing required Azure env → exit 2; flags override env; missing keys from `infra/outputs.json` unless `--no-terraform`.
- env: canonical only — `AZURE_LOCATION`, `AZURE_RESOURCE_GROUP`, `AZURE_STORAGE_ACCOUNT_URL`, `AZURE_STORAGE_RESOURCE_ID`, `AZURE_SEARCH_ENDPOINT`, `AZURE_AI_PROJECT_ENDPOINT`, `AZURE_AI_PROJECT_RESOURCE_ID`, `AZURE_AI_SERVICES_ENDPOINT`, `AZURE_AI_PROJECT_PRINCIPAL_ID`; never `SEARCH_ENDPOINT` or `FOUNDRY_PROJECT_ENDPOINT`; optional `AZURE_STORAGE_CONNECTION_STRING` generate-only never committed; flags > process env > `infra/outputs.json` (keys = canonical names, unwrap .value); ! committed `.env.example`; stray `.env` gitignored never loaded
- search: KS `PUT .../knowledgesources/ks-credit-policies?api-version=2026-08-01-preview` kind azureBlob; connectionString `ResourceId={AZURE_STORAGE_RESOURCE_ID}` no trailing semicolon (400 → retry with semicolon); container `credit-policies`; embedding `text-embedding-3-large`; `contentExtractionMode: minimal`. KS `PUT .../knowledgesources/ks-client-applications` same kind/api-version/connectionString/embedding/extraction; container `client-applications`
- kb: KB `PUT .../knowledgebases/kb-credit-policies` `outputMode: extractiveData` (not `extractedData`) `retrievalReasoningEffort.kind: low` model `gpt-5-mini`; knowledge sources `ks-credit-policies` + `ks-client-applications`; retrieve POST `messages`; tests may set effort `minimal`
- arm: `PUT {project_resource_id}/connections/conn-kb-credit-policies?api-version=2025-10-01-preview` authType ProjectManagedIdentity category RemoteTool target KB MCP URL audience `https://search.azure.com/`
- agent: Foundry `api-version=v1` `PromptAgentDefinition` model `gpt-5-mini` MCPTool `knowledge_base_retrieve` connection `conn-kb-credit-policies`; omit stored temperature on `gpt-5*` (invoke 400); temperature=0 on other models; invoke Responses API `agent_reference`; token scope `https://ai.azure.com/.default`
- names: env ∈ {dev1, prd1}; RG `rg-credit-policy-${env}`; storage `stcp${resourceToken}`; search `srch-cp-${resourceToken}` SKU basic; Foundry `aif-cp-${resourceToken}` kind AIServices S0; project `credit-policy-demo`; chat deploy `gpt-5-mini` sku GlobalStandard capacity 50 (=50k TPM); embed `text-embedding-3-large` capacity 20; KS `ks-credit-policies` + `ks-client-applications`; KB `kb-credit-policies`; conn `conn-kb-credit-policies`; agent `credit-policy-agent`; blob containers `credit-policies` + `client-applications`
- file: `corpus/facts.yaml` SoT unique keys; `corpus/templates/*.md.j2`; committed `data/credit-policies/*.md` + `manifest.json`; gitignored `data/client-applications/*.md` + `manifest.json`; commit application prompts+schema+gitignore; unit fixtures `tests/fixtures/client-applications/`; `agents/credit-policy-agent.instructions.md`; `tests/fixtures/golden_queries.yaml` (18 ids)
- infra: terraform CLI; `infra/*.tf`; `infra/dev1.tfvars` + `infra/prd1.tfvars`; apply `-var-file=<env>.tfvars` env ∈ {dev1, prd1} ! `credit-policy-demo`; Makefile `ENV` same set default `dev1`; GHA release backend key `prd1`; azurerm backend Azure AD; bootstrap `az` CLI not terraform ! `infra/backend/` — RG `rg-credit-policy-tfstate` container `tfstate` account `sttfstlab5` ! workload `stcp*`; Blob Data Contributor on account; state key `<env>.tfstate`; standing init `-reconfigure`; `gmake infra-backend-create` `az group`/`storage account`/`container create` / `infra-backend-show` `az` show / `infra-backend-destroy` `az group delete`; `gmake infra-create` apply then `terraform output -json` → `infra/outputs.json` / `infra-show` print state / `infra-destroy` drop stack + `infra/outputs.json`; storage `public_network_access = "Enabled"` ! deprecated `public_network_access_enabled`; no azure.yaml; no azd; no agent as terraform resource; no KS in Terraform; `*.tfstate` + `infra/outputs.json` gitignored never committed
- pytest: markers `unit` `ingestion` `retrieval` `agent` `teams`; live skip w/o canonical env; teams skip unless `E2E_TEAMS=1` (flag set and no client → skip not fail)
- make: `gmake test` → `uv run pytest` (addopts `-m unit`); `gmake check` ruff format --check + ruff check + test; `gmake e2e` `uv run pytest -m "ingestion or retrieval or agent" --override-ini addopts=` (`FILE=` scopes one file); GHA unit `uv run pytest`; ! `talos test` Click cmd
- corpus_ids: CP-RML-2026-01, CP-CRE-2026-01, CP-UCL-2026-01, CP-SME-2026-01, CP-EXC-2026-01, CP-PRO-2026-01, CP-COL-2026-01, CP-DOC-2026-01, CP-RPL-2026-01, CP-ESG-2026-01, CP-CND-2026-01, CP-AUTH-2026-01
- golden: Q-RML-LTV-OO, Q-RML-DTI, Q-CRE-DSCR, Q-UCL-MAX, Q-SME-PG, Q-COL-AVM, Q-AUTH-RM, Q-CMP-LTV-CRE-ESG, Q-CMP-CONSTRUCTION, Q-NEG-AUTO, Q-NEG-SOVEREIGN, Q-AMB-LTV, Q-CIT-PROHIBITED, Q-MT-EXCEPTION, Q-MT-ESG-FOLLOWUP, Q-ADV-JAILBREAK, Q-ADV-INVENT, Q-DOC-SE

## §V INVARIANTS

V1: grounded-only — agent factual claims ! from `knowledge_base_retrieve` output; judgements: thresholds from policy retrieve hits, application facts from application retrieve hits after id or name match; never training-data LTV/DTI/DSCR/tenors/committees; empty policy retrieve → exact `That is not in the published policies.`
V2: synthetic-demo — first visible line every policy and every generated application `SYNTHETIC — DEMO ONLY`; asked if real → disclose synthetic demo; no production credit decisioning; SyntheticBorrower ! real PII, ! real national-id formats
V3: citation-id — every factual claim cites Learn glyph `【message_idx:search_idx†source_name】`; source_name = policy blob filename or original blob URL or `policy_id`; ! invent section headings as citation keys; judgement findings ! cite application blobs
V4: stack-thin — v1 = Foundry prompt agent + Foundry IQ MCP project connection + portal/REST Teams publish; ! custom Microsoft 365 Agents SDK host; ! native knowledge tool; allowed_tools `["knowledge_base_retrieve"]`; KB `kb-credit-policies` lists two KS (`ks-credit-policies`, `ks-client-applications`); ! second KB, ! second MCP conn, ! second agent
V5: corpus-shape — PolicyCorpus 12 Markdown files from `corpus/facts.yaml`; each fact value appears verbatim; uniqueness per fact key not numeric token (shared 55%/65%/90 days/12 months intentional); dual-write local+blob; commit generated policy MD. ApplicationCorpus 3 local slots `data/client-applications/` one per `accepted`|`rejected`|`missing-data`; gitignore `*.md` + `manifest.json`; ! commit generated applications; unit fixtures `tests/fixtures/client-applications/`
V6: search-preview — Search REST/SDK api-version `2026-08-01-preview`; pin `azure-search-documents==12.1.0b2`; SKU Basic (MI); ! Free
V7: kb-extractive — KB `outputMode: extractiveData` (REST enum; not `extractedData`); default effort `low`; tests may override retrieve `minimal`
V8: models — chat + KB planning `gpt-5-mini`; embedding `text-embedding-3-large`; ! `gpt-5.4-mini` v1; ! deprecated `gpt-4.1-mini` for KB
V9: region — default `AZURE_LOCATION=swedencentral`; ! new Search eastus eastus2 westus westus3; ! westus2 (no GS `gpt-5-mini`); backups uksouth francecentral canadaeast centralus
V10: talos-cli — one Click package `talos` (`[project.scripts] talos = "talos.cli:cli"`); CPython 3.14; ! PEP 723; missing required Azure env → exit 2; `talos generate` Click group: `policy` + `application`; bare `talos generate` → help exit 2; ! chain generate → deploy
V11: deploy-split — storage/search/Foundry/RBAC/deployments via terraform apply; blob-sync of local corpora + KS/KB/indexer-run/connection/agent via `talos deploy`; ! KS in Terraform
V12: indexer-on-demand — omit `ingestionSchedule` v1; after each KS PUT and later blob uploads POST generated indexer from `createdResources.indexer` (policy + application); 409 already-running = success; ! edit generated indexer/skillset/index
V13: ks-resourceid — blob KS connectionString `ResourceId={AZURE_STORAGE_RESOURCE_ID}` no trailing `;`; create 400 → retry with `;`
V14: agent-endpoint — omit stored temperature on `gpt-5*` (invoke 400); temperature=0 on other models; pin Active version via merge-patch only `agent_endpoint.version_selector`; after Teams publish ! replace `protocol_configuration` or `authorization_schemes`; `--skip-endpoint-patch` default on if activity enabled
V15: env-contract — Terraform outputs + pytest + talos read only canonical env names; flags override process env; missing keys from `infra/outputs.json` (`terraform output -json` shape, unwrap .value) unless `--no-terraform`; never spawn `terraform output` at talos/pytest runtime; never overwrite set keys; ! load repo-root `.env`
V16: rbac-mcp — project SystemAssigned MI → Search Index Data Reader; Search MI → Storage Blob Data Reader + Cognitive Services User; MCP authenticates as project MI; Teams 403 after playground works → also Search Index Data Reader on agent instance identity
V17: secrets — Microsoft Entra ID / DefaultAzureCredential operator path; keys may exist on resource; never commit keys/connection strings; stray `.env` gitignored never loaded; ! `disableLocalAuth: true`
V18: teams-just-you — v1 Direct publish Just you (`BotServiceRbac`); sideload downloaded manifest ZIP in-scope fallback; register `Microsoft.BotService`; operator needs Azure Bot Service Contributor on RG
V19: golden-layers — 18 catalog ids in `tests/fixtures/golden_queries.yaml`; default layers `[retrieval, agent]` never `teams`; retrieval ! assert refusal sentence `not in the published policies`; comparison recall_mode `all`; negative/adversarial = agent layer
V20: pytest-default-unit — `addopts = "-m unit"`; live markers skip w/o env; `teams` skip unless `E2E_TEAMS=1`; flag set and no Activity client → skip not fail; unit via `gmake test` → `uv run pytest`; ! `talos test` Click cmd
V21: tpm-capacity — Foundry Models `sku.capacity` 1 = 1000 TPM; chat default capacity 50 (=50k TPM) not 50000
V22: hash-skip — blob overwrite skip via metadata `content_sha256` lowercase hex SHA-256 UTF-8 bytes; ! Azure Content-MD5
V23: no-appinsights — v1 Terraform ! Application Insights; traces = Foundry playground + Search `includeActivity`
V24: wait-gate — `talos deploy --wait` polls both KS until each `lastSynchronizationState.endTime` set and `itemsUpdatesFailed == 0` and policy processed ≥ 12 and application processed ≥ 3; timeout 15 min
V25: watermark-refuse — instructions refuse jailbreak/override/invent (`I cannot override published credit policy...`); ! echo pasted PII; ! log document bodies or user prompts at INFO (query ids only)
V26: dual-write-auth — generate and deploy Azure path: connection string if set else DefaultAzureCredential + `AZURE_STORAGE_ACCOUNT_URL`; operator Storage Blob Data Contributor; containers private no anonymous
V27: instructions-file — `agents/credit-policy-agent.instructions.md` loaded verbatim into `PromptAgentDefinition.instructions`; file contains EvaluationMode (id or customer_name; ask if missing; policy-only citations)
V28: fact-literals — threshold sentences use facts.yaml literals (`80%`, `USD 50,000`, committee names) no rounding no synonyms in SoT sentence
V29: tfvars-envs — terraform apply `-var-file=dev1.tfvars` or `prd1.tfvars`; `environment_name` ∈ {dev1, prd1}; ! `credit-policy-demo`; Makefile `ENV` same set; GHA release backend key `prd1`
V30: remote-state — azurerm backend `use_azuread_auth`; bootstrap via `az` CLI not terraform ! `infra/backend/`; RG `rg-credit-policy-tfstate` container `tfstate`; account `sttfstlab5` ! workload `stcp*`; reconstructible after clone; blob key `<env>.tfstate`; standing `terraform init -reconfigure` backend-config `key=<env>.tfstate`; `*.tfstate` gitignored never committed
V31: evaluation-keys — evaluate by `application_id` or `customer_name` only; both missing → agent asks, ! judge; name not unique → disambiguate; type nickname (`accepted`) ! identifier
V32: application-generate — `talos generate application` calls Foundry `gpt-5-mini`; unique SyntheticBorrower (name, fictional address, `SYN-######` customer_id, `@example.invalid` email); `--type` or `--all`; `--force` overwrite slot; facts.yaml literals drive `accepted`|`rejected`|`missing-data`; validate+1 retry; ! real PII

## §T TASKS

id|status|task|cites
T1|x|init talos Click CLI deploy+test, CPython 3.14, plan docs, unit CLI tests, GHA unit workflow|V10,I.cmd
T2|x|add talos generate local-only: facts.yaml, jinja templates, 12 MD + manifest, watermark, fact-key uniqueness|V2,V5,V28,I.cmd,I.file
T3|x|add corpus contract tests + 18 golden queries yaml|V5,V19,V20,I.pytest,I.golden
T4|x|add azd+Bicep storage Search Basic Foundry project-MI models RBAC canonical outputs location swedencentral|V6,V8,V9,V11,V16,V17,V21,V23,I.infra,I.env,I.names
T5|x|extend generate dual-write blobs content_sha256 skip|V5,V22,V26,I.cmd
T6|x|prove live talos deploy blob-sync both corpora --wait both KS (policy ≥12, application ≥3) two indexers KB two sources ARM MCP agent temperature=0 version_selector merge-patch|V4,V7,V11,V12,V13,V14,V22,V24,I.cmd,I.search,I.kb,I.arm,I.agent
T7|x|add live pytest markers ingestion retrieval agent; evaluate-by-id, evaluate-by-name, ask-when-missing, one case per ApplicationType; unit fixtures `tests/fixtures/client-applications/`|V1,V3,V19,V20,V31,I.pytest
T8|x|add Teams Just-you runbook + teams marker skip unless E2E_TEAMS=1; sideload fallback; evaluate-by-id and evaluate-by-name|V16,V18,V20,V31,I.agent
T9|x|optional talos publish REST + hosted-agent spike doc|V4,V18,I.cmd
T10|x|load repo-root .env for missing canonical env in talos+pytest; flags>process>.env>azd; gitignore .env|V15,V17,I.env,I.cmd,I.pytest
T11|x|drop `.env` load from talos+pytest; flags>process>azd; drop `.env.example`; keep gitignore `.env`|V15,V17,I.env,I.cmd,I.pytest
T12|x|swap azd+Bicep → terraform CLI; drop azure.yaml; env fill `terraform -chdir=infra output -json`; flag `--no-terraform`|V11,V15,V23,I.infra,I.env,I.cmd
T13|x|add azurerm backend + bootstrap; migrate-state; `infra/dev1.tfvars`+`prd1.tfvars`; drop credit-policy-demo; Makefile ENV∈{dev1,prd1}; GHA release prd1|V29,V30,I.infra,I.names
T14|x|swap infra-backend-* terraform → az CLI; drop `infra/backend/`|V30,I.infra
T15|x|Makefile infra-create emit `infra/outputs.json`; talos+pytest fill missing env from file; drop live `terraform output`; gitignore file; infra-destroy drop file|V15,I.infra,I.env,I.cmd
T16|x|swap deprecated `public_network_access_enabled` → `public_network_access` on storage (`"Enabled"`); search/foundry same iff provider exposes string attr|I.infra
T17|x|swap standing init assert+docs `-migrate-state` → `-reconfigure`|V30,B1,I.infra
T18|x|swap `talos generate` → Click group `policy` (existing render, ! deploy) + `application`; bare generate → help exit 2|V10,I.cmd
T19|x|add `talos generate application`: unique SyntheticBorrower, `--type`/`--all`/`--force`, validate+retry, gitignore `data/client-applications/*.md`+manifest, optional blob hash-skip|V2,V5,V8,V22,V26,V32,I.cmd,I.file
T20|x|extend `agents/credit-policy-agent.instructions.md` EvaluationMode: id or customer_name, ask if missing, judgement cites policy docs only|V1,V3,V27,V31,I.agent
T21|x|drop `talos test` Click; Makefile `test` → `uv run pytest`; `check` calls test; GHA unit `uv run pytest`; drop CLI pytest.main + forwarding test + GHA `talos test` assert|V20,I.cmd,I.make,I.pytest

## §B BUGS

id|date|cause|fix
B1|2026-09-13|standing infra-init spec required `-migrate-state` after remote backend live; recipe is `-reconfigure`|V30
