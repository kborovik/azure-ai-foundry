# Teams Just-you runbook

Publish `credit-policy-agent` to Microsoft Teams as **Just you** (`BotServiceRbac`). This is a demo 1:1 chat, not a production origination channel.

## Prerequisites

- Operator is Azure Bot Service Contributor on the workload resource group `rg-credit-policy-<env>`.
- Register the `Microsoft.BotService` resource provider on the subscription:

```bash
az provider register --namespace Microsoft.BotService
```

- `uv run talos deploy --wait` has landed both knowledge sources (`ks-credit-policies`, `ks-client-applications`) on `kb-credit-policies`.
- Three synthetic applications exist locally (`uv run talos generate application --all --local-only`) and were blob-synced by deploy.

## Direct publish (Just you)

1. Open the Foundry project `credit-policy-demo`.
2. Open agent `credit-policy-agent`.
3. Publish to Microsoft Teams → **Just you** (BotServiceRbac).
4. After publish, do **not** replace `protocol_configuration` or `authorization_schemes`. Later `talos deploy` skips the endpoint merge-patch when Activity is already enabled (`--skip-endpoint-patch` is implied).

## Sideload fallback

If Direct publish is blocked in the tenant:

1. Download the Teams app manifest ZIP from the Foundry publish pane.
2. In Teams (desktop), Apps → Manage your apps → Upload a custom app → sideload the ZIP.
3. Sideload is in-scope for this demo; it is not a store submission.

## RBAC if Teams 403 after playground works

Grant **Search Index Data Reader** on the Azure AI Search service to the **agent instance identity** (in addition to the project system-assigned MI). Playground uses the project MI; Teams uses the agent instance identity.

Also confirm:

- Project MI → Search Index Data Reader
- Search MI → Storage Blob Data Reader + Cognitive Services User
- MCP connection `conn-kb-credit-policies` authenticates as the project MI (`ProjectManagedIdentity`, audience `https://search.azure.com/`)

## Evaluation prompts

Identify an application by `application_id` or `customer_name` only. Type nicknames (`accepted`, `rejected`, `missing-data`) are not identifiers.

**Evaluate by id**

```
Evaluate application CA-ACCEPTED-2026-01 against published credit policy.
```

**Evaluate by name**

```
Evaluate the application for Helene Voss.
```

If both identifiers are missing, the agent asks for one and does not judge.

Judgement findings cite policy documents only (Learn glyph). Application blobs are context, not citation keys.

## Pytest

Teams tests use marker `teams` and skip unless `E2E_TEAMS=1`. If the flag is set but the agent has no Activity client, tests skip (not fail).

```bash
E2E_TEAMS=1 uv run pytest -m teams --override-ini addopts=
```
