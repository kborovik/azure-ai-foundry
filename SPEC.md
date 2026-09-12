# SPEC — Bank Credit Policy Agent Demo

## §G GOAL

Demo Foundry prompt agent answers credit-policy questions only from 12 synthetic Markdown docs in Foundry IQ, w/ citations, in Microsoft Teams 1:1 — not a production credit system.

## §C CONSTRAINTS

- demo: no origination workflow, no real borrower PII, no real bank IP, no document ACLs / Purview
- thin stack: Foundry Agent Service prompt agent + Foundry IQ + portal/REST Teams publish; hosted agents + Microsoft 365 Agents SDK = alternative not v1
- Markdown-only corpus v1; no PDF
- no multi-agent, no write-back to core banking
- public network access on; no Private Link / CMK
- KB returns extractive chunks; agent LLM synthesizes; no KB `answerSynthesis`
- Search SKU Basic (MI required); semantic-ranker concurrency 2 per SU → serialize demo chats
- Search REST `2026-08-01-preview` (preview risk); pin client `azure-search-documents==12.1.0b2`
- CPython 3.14; `requires-python = ">=3.14"`; `[tool.uv] python-preference = "managed"`; no PEP 723 scripts
- one CLI `talos`; GitHub Actions + operators call `uv run talos`
- default region `swedencentral`; never new Search in eastus/eastus2/westus/westus3; never westus2 (no GlobalStandard `gpt-5-mini`)
- local auth keys allowed on resource; never committed; do not set `disableLocalAuth: true`
- no Application Insights in v1 Bicep
- default CI = unit corpus/CLI tests; live Azure behind pytest markers; Teams opt-in `E2E_TEAMS=1`

## §I INTERFACES

- cmd: `uv run talos generate` → render facts+templates, write `data/credit-policies/`, optional blob upload; `--local-only` / `--azure-only` mutex; `--dry-run` / `--force` / `--fail-if-missing-azure` / `--no-azd`; exit 0 ok, 1 render/upload, 2 Azure missing, 3 facts invalid; does not run indexer. `uv run talos deploy` → idempotent KS PUT, POST generated indexer, poll `--wait`, KB PUT, ARM MCP connection, agent `create_version` temperature=0, merge-patch `version_selector`; `--skip-indexer-run` / `--skip-endpoint-patch` / `--dry-run` / `--no-azd`. `uv run talos test` → pytest passthrough; default `addopts = "-m unit"`. Missing required Azure env → exit 2; flags override env; gaps from `azd env get-values` unless `--no-azd`.
- env: canonical only — `AZURE_LOCATION`, `AZURE_RESOURCE_GROUP`, `AZURE_STORAGE_ACCOUNT_URL`, `AZURE_STORAGE_RESOURCE_ID`, `AZURE_SEARCH_ENDPOINT`, `AZURE_AI_PROJECT_ENDPOINT`, `AZURE_AI_PROJECT_RESOURCE_ID`, `AZURE_AI_SERVICES_ENDPOINT`, `AZURE_AI_PROJECT_PRINCIPAL_ID`; never `SEARCH_ENDPOINT` or `FOUNDRY_PROJECT_ENDPOINT`; optional `AZURE_STORAGE_CONNECTION_STRING` generate-only never committed
- search: KS `PUT .../knowledgesources/ks-credit-policies?api-version=2026-08-01-preview` kind azureBlob; connectionString `ResourceId={AZURE_STORAGE_RESOURCE_ID}` no trailing semicolon (400 → retry with semicolon); container `credit-policies`; embedding `text-embedding-3-large`; `contentExtractionMode: minimal`
- kb: KB `PUT .../knowledgebases/kb-credit-policies` `outputMode: extractiveData` (not `extractedData`) `retrievalReasoningEffort.kind: low` model `gpt-5-mini`; retrieve POST `messages`; tests may set effort `minimal`
- arm: `PUT {project_resource_id}/connections/conn-kb-credit-policies?api-version=2025-10-01-preview` authType ProjectManagedIdentity category RemoteTool target KB MCP URL audience `https://search.azure.com/`
- agent: Foundry `api-version=v1` `PromptAgentDefinition` model `gpt-5-mini` MCPTool `knowledge_base_retrieve` connection `conn-kb-credit-policies` temperature=0; invoke Responses API `agent_reference`; token scope `https://ai.azure.com/.default`
- names: RG `rg-credit-policy-${env}`; storage `stcp${resourceToken}`; search `srch-cp-${resourceToken}` SKU basic; Foundry `aif-cp-${resourceToken}` kind AIServices S0; project `credit-policy-demo`; chat deploy `gpt-5-mini` sku GlobalStandard capacity 50 (=50k TPM); embed `text-embedding-3-large` capacity 20; KS `ks-credit-policies`; KB `kb-credit-policies`; conn `conn-kb-credit-policies`; agent `credit-policy-agent`
- file: `corpus/facts.yaml` SoT unique keys; `corpus/templates/*.md.j2`; committed `data/credit-policies/*.md` + `manifest.json`; `agents/credit-policy-agent.instructions.md`; `tests/fixtures/golden_queries.yaml` (18 ids)
- infra: `azd` + `infra/main.bicep`; `azure.yaml` module `main` (not `main.bicep`); no agent as azd service; no KS in Bicep
- pytest: markers `unit` `ingestion` `retrieval` `agent` `teams`; live skip w/o canonical env; teams skip unless `E2E_TEAMS=1` (flag set and no client → skip not fail)
- corpus_ids: CP-RML-2026-01, CP-CRE-2026-01, CP-UCL-2026-01, CP-SME-2026-01, CP-EXC-2026-01, CP-PRO-2026-01, CP-COL-2026-01, CP-DOC-2026-01, CP-RPL-2026-01, CP-ESG-2026-01, CP-CND-2026-01, CP-AUTH-2026-01
- golden: Q-RML-LTV-OO, Q-RML-DTI, Q-CRE-DSCR, Q-UCL-MAX, Q-SME-PG, Q-COL-AVM, Q-AUTH-RM, Q-CMP-LTV-CRE-ESG, Q-CMP-CONSTRUCTION, Q-NEG-AUTO, Q-NEG-SOVEREIGN, Q-AMB-LTV, Q-CIT-PROHIBITED, Q-MT-EXCEPTION, Q-MT-ESG-FOLLOWUP, Q-ADV-JAILBREAK, Q-ADV-INVENT, Q-DOC-SE

## §V INVARIANTS

V1: grounded-only — agent factual claims ! from `knowledge_base_retrieve` output; never training-data LTV/DTI/DSCR/tenors/committees; empty retrieve → exact `That is not in the published policies.`
V2: synthetic-demo — first visible line every policy `SYNTHETIC — DEMO ONLY`; asked if real → disclose synthetic demo; no production credit decisioning
V3: citation-id — every factual claim cites Learn glyph `【message_idx:search_idx†source_name】`; source_name = blob filename or original blob URL or `policy_id`; ! invent section headings as citation keys
V4: stack-thin — v1 = Foundry prompt agent + Foundry IQ MCP project connection + portal/REST Teams publish; ! custom Microsoft 365 Agents SDK host; ! native knowledge tool; allowed_tools `["knowledge_base_retrieve"]`
V5: corpus-shape — 12 Markdown files from `corpus/facts.yaml`; each fact value appears verbatim; uniqueness per fact key not numeric token (shared 55%/65%/90 days/12 months intentional); dual-write local+blob; commit generated MD
V6: search-preview — Search REST/SDK api-version `2026-08-01-preview`; pin `azure-search-documents==12.1.0b2`; SKU Basic (MI); ! Free
V7: kb-extractive — KB `outputMode: extractiveData` (REST enum; not `extractedData`); default effort `low`; tests may override retrieve `minimal`
V8: models — chat + KB planning `gpt-5-mini`; embedding `text-embedding-3-large`; ! `gpt-5.4-mini` v1; ! deprecated `gpt-4.1-mini` for KB
V9: region — default `AZURE_LOCATION=swedencentral`; ! new Search eastus eastus2 westus westus3; ! westus2 (no GS `gpt-5-mini`); backups uksouth francecentral canadaeast centralus
V10: talos-cli — one Click package `talos` (`[project.scripts] talos = "talos.cli:cli"`); CPython 3.14; ! PEP 723; missing required Azure env → exit 2
V11: deploy-split — storage/search/Foundry/RBAC/deployments via azd+Bicep; KS/KB/indexer-run/connection/agent via `talos deploy`; ! KS in Bicep
V12: indexer-on-demand — omit `ingestionSchedule` v1; after KS PUT and later blob uploads POST generated indexer from `createdResources.indexer`; 409 already-running = success; ! edit generated indexer/skillset/index
V13: ks-resourceid — blob KS connectionString `ResourceId={AZURE_STORAGE_RESOURCE_ID}` no trailing `;`; create 400 → retry with `;`
V14: agent-endpoint — `temperature=0`; pin Active version via merge-patch only `agent_endpoint.version_selector`; after Teams publish ! replace `protocol_configuration` or `authorization_schemes`; `--skip-endpoint-patch` default on if activity enabled
V15: env-contract — Bicep outputs + pytest + talos read only canonical env names; flags override process env; remaining gaps from `azd env get-values` (strip quotes, skip blank/#) unless `--no-azd`
V16: rbac-mcp — project SystemAssigned MI → Search Index Data Reader; Search MI → Storage Blob Data Reader + Cognitive Services User; MCP authenticates as project MI; Teams 403 after playground works → also Search Index Data Reader on agent instance identity
V17: secrets — Microsoft Entra ID / DefaultAzureCredential operator path; keys may exist on resource; never commit keys/connection strings; ! `disableLocalAuth: true`
V18: teams-just-you — v1 Direct publish Just you (`BotServiceRbac`); sideload downloaded manifest ZIP in-scope fallback; register `Microsoft.BotService`; operator needs Azure Bot Service Contributor on RG
V19: golden-layers — 18 catalog ids in `tests/fixtures/golden_queries.yaml`; default layers `[retrieval, agent]` never `teams`; retrieval ! assert refusal sentence `not in the published policies`; comparison recall_mode `all`; negative/adversarial = agent layer
V20: pytest-default-unit — `addopts = "-m unit"`; live markers skip w/o env; `teams` skip unless `E2E_TEAMS=1`; flag set and no Activity client → skip not fail
V21: tpm-capacity — Foundry Models `sku.capacity` 1 = 1000 TPM; chat default capacity 50 (=50k TPM) not 50000
V22: hash-skip — blob overwrite skip via metadata `content_sha256` lowercase hex SHA-256 UTF-8 bytes; ! Azure Content-MD5
V23: no-appinsights — v1 Bicep ! Application Insights; traces = Foundry playground + Search `includeActivity`
V24: wait-gate — `talos deploy --wait` polls KS status until `lastSynchronizationState.endTime` set and `itemsUpdatesFailed == 0` and processed ≥ 12; timeout 15 min
V25: watermark-refuse — instructions refuse jailbreak/override/invent (`I cannot override published credit policy...`); ! echo pasted PII; ! log document bodies or user prompts at INFO (query ids only)
V26: dual-write-auth — generate Azure path: connection string if set else DefaultAzureCredential + `AZURE_STORAGE_ACCOUNT_URL`; operator Storage Blob Data Contributor; container private no anonymous
V27: instructions-file — `agents/credit-policy-agent.instructions.md` loaded verbatim into `PromptAgentDefinition.instructions`
V28: fact-literals — threshold sentences use facts.yaml literals (`80%`, `USD 50,000`, committee names) no rounding no synonyms in SoT sentence

## §T TASKS

id|status|task|cites
T1|x|init talos Click CLI deploy+test, CPython 3.14, plan docs, unit CLI tests, GHA unit workflow|V10,I.cmd
T2|x|add talos generate local-only: facts.yaml, jinja templates, 12 MD + manifest, watermark, fact-key uniqueness|V2,V5,V28,I.cmd,I.file
T3|x|add corpus contract tests + 18 golden queries yaml|V5,V19,V20,I.pytest,I.golden
T4|x|add azd+Bicep storage Search Basic Foundry project-MI models RBAC canonical outputs location swedencentral|V6,V8,V9,V11,V16,V17,V21,V23,I.infra,I.env,I.names
T5|.|extend generate dual-write blobs content_sha256 skip|V5,V22,V26,I.cmd
T6|.|prove live talos deploy --wait KS indexer KB extractiveData ARM MCP agent temperature=0 version_selector merge-patch|V4,V7,V12,V13,V14,V24,I.cmd,I.search,I.kb,I.arm,I.agent
T7|.|add live pytest markers ingestion retrieval agent|V1,V3,V19,V20,I.pytest
T8|.|add Teams Just-you runbook + teams marker skip unless E2E_TEAMS=1; sideload fallback|V16,V18,V20,I.agent
T9|.|optional talos publish REST + hosted-agent spike doc|V4,V18,I.cmd

## §B BUGS

id|date|cause|fix
