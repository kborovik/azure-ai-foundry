# Bank Credit Policy Agent Demo

A Microsoft Teams assistant that evaluates client applications against published credit policy and helps a credit officer process the file — with citations.

## Executive Summary

Credit officers process applications against published policy: read the filing, check LTV, DTI, and required documents, and record a decision. Today that means paging through policy PDFs while the deal is live. Generic chat models invent thresholds, committees, and eligibility rules.

This repository is a **demo**, not a production origination system. It shows a Foundry Agent Service assistant that evaluates client applications and helps the credit officer work the file in Microsoft Teams, one-to-one. Name an application by number or customer; the agent compares it to twelve Contoso Demo Bank credit-policy documents, flags missing items, and returns a cited judgement — accept, reject, or missing-data. Policy lookup is in service of that workflow. If the published policies do not cover the question, the agent says so rather than guessing.

## How it works

**How a credit officer gets an answer**

```mermaid
flowchart TB
  A[Credit Officer<br/>asks in Teams] --> B[Credit Policy Agent]
  B --> C[Knowledge base]
  C --> D[Policy question:<br/>cited answer, or not in the published policies]
  C --> E[Named application:<br/>cited accept, reject, or missing-data]
```

**The agent does two jobs:**

- **Policy Q&A** — quote the number, the conditions, and the source document.
- **Application evaluation** — compare a sample filing to published policy and return accept, reject, or missing-data. Findings cite policy documents only.

## Design

One agent, one knowledge base, one 1:1 Teams chat. Published policy is the source of truth; sample applications are the files being judged; the model is not.

**One agent, one knowledge base, 1:1 chat**

```mermaid
flowchart TB
  subgraph People
    Officer[Credit Officer]
  end

  subgraph Channel
    Teams[Microsoft Teams<br/>1:1 chat]
  end

  subgraph Foundry["Azure Foundry Agent Service"]
    Agent[Prompt Agent]
    KB[Knowledge Base]
  end

  subgraph Documents
    Pol[Published credit policies]
    Apps[Sample client applications]
  end

  Officer --> Teams
  Teams --> Agent
  Agent --> KB
  KB --> Pol
  KB --> Apps
```

**From Teams chat to a cited answer**

```mermaid
sequenceDiagram
  participant U as Microsoft Teams
  participant BOT as Azure Bot
  participant A as Foundry Agent
  participant KB as Foundry IQ

  U->>BOT: 1:1 chat
  BOT->>A: message
  A->>KB: look up documents
  KB-->>A: passages and citations
  A->>A: grounded answer, or refuse if empty
  A-->>BOT: text and citations
  BOT-->>U: 1:1 reply
```

**How documents reach the knowledge base**

Credit policies live in this repository. Sample applications are generated for the demo. Both are stored, then indexed, then served from one knowledge base.

```mermaid
flowchart TB
  Pol[Credit policies<br/>in this repository] --> Store[Document storage]
  Apps[Sample applications<br/>generated for the demo] --> Store
  Store --> Search[Enterprise search]
  Search --> KB[Knowledge base]
```

Azure underneath is a single subscription with document storage, enterprise search, a Foundry project, and the chat and embedding models the agent uses.

**Azure resources**

```mermaid
flowchart TB
  Store[Document storage] --> Search[Enterprise search]
  Search --> Project[Foundry project]
  Models[Chat and embedding models] --> Project
  Project --> Agent[Credit Policy Agent]
```

## Deploying the demo

Four steps take this repository to a working Teams chat. Terraform in `infra/` stands up Azure; the `talos` CLI loads `data/`, creates the agent from `agents/`, and publishes it to Teams.

```mermaid
flowchart TB
  S1[1. infra/<br/>Azure resources] --> S2[2. data/<br/>knowledge base]
  S2 --> S3[3. agents/<br/>prompt agent]
  S3 --> S4[4. Teams<br/>1:1 chat]
```

1. **Azure resources (`infra/`).** Terraform creates document storage, enterprise search, a Foundry project, and the models. Two environments (`dev1`, `prd1`) share that shape so a lab demo matches production.

2. **Knowledge base (`data/`).** The twelve credit policies (rendered from `corpus/` into `data/credit-policies/`) and the sample applications in `data/client-applications/` are stored and indexed. Until this step finishes, the agent has nothing grounded to quote.

3. **Prompt agent (`agents/`).** Foundry creates the agent from the instructions in `agents/`: answer only from the knowledge base, and cite the source. It cannot invent LTV, DTI, or committee names, and it will not override published policy.

4. **Teams.** Publish as a private 1:1 chat for the operator. If the tenant blocks that path, sideload the Teams app instead. A credit officer then asks a policy question, or names an application to evaluate. See [docs/teams.md](docs/teams.md).

A production release repeats steps 2–4 against the live environment: refresh documents, re-index, keep the agent pointed at the published policies. Every code change is tested automatically; secrets are not stored in git.

This demo does not ship a second, container-hosted agent or a custom Teams bot. Foundry already bridges the prompt agent into Teams. Reopen that work only if a later version needs custom code inside the agent loop. See [docs/hosted-agents.md](docs/hosted-agents.md).
