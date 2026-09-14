# Hosted agents spike (not v1)

This note records why **hosted agents** and a custom **Microsoft 365 Agents SDK** host stay out of v1. It is not an implementation plan.

v1 is a Foundry **prompt agent** plus Foundry IQ (MCP project connection) plus **portal or REST Teams publish**. That stack is the thin path: one agent, one knowledge base, one MCP connection, `allowed_tools = ["knowledge_base_retrieve"]`. Custom hosting is an alternative, not a second product in this repo.

## What hosted agents are

[Hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents) are container images that Foundry Agent Service runs for you. You pick the framework (Agent Framework, LangGraph, Semantic Kernel, or custom code), push an image to Azure Container Registry, and the platform assigns an agent identity and endpoint. Sessions run in VM-isolated sandboxes with CPU/memory SKUs, idle timeout, and optional Application Insights.

That is a different runtime from a prompt agent defined by `PromptAgentDefinition` + tools. Hosted agents exist to bring your own orchestration, webhooks (Invocations protocol), or long-running state. They are not required to answer credit-policy questions from extractive Foundry IQ chunks.

## What the Microsoft 365 Agents SDK is

The Microsoft 365 Agents SDK is a **custom host**: you run a process that speaks the Activity protocol to Azure Bot Service and Microsoft Teams. Foundry's built-in Teams publish already bridges a prompt agent to Activity (`BotServiceRbac` for Just you). A custom SDK host would duplicate that channel adapter in this repository.

## Why not v1

- The demo needs cited policy answers and synthetic application evaluations. A prompt agent with `knowledge_base_retrieve` covers that.
- Hosted agents add container build, registry, sandbox SKUs, and session lifecycle. None of that is in the Terraform stack or `talos deploy`.
- A custom Agents SDK host would be a second agent surface. v1 forbids a second agent, a second knowledge base, and a second MCP connection.
- v1 Terraform does not include Application Insights. Hosted-agent observability assumes it.
- Teams Just you already ships via portal Direct publish or `uv run talos publish` (REST). Sideload of the downloaded manifest ZIP remains the fallback.

## When to reopen

Reopen hosted agents or the Agents SDK only if a later spec needs:

- custom code in the agent loop (not instructions + MCP retrieve)
- webhook or non-OpenAI payloads
- a self-hosted Activity adapter instead of Foundry's Microsoft 365 publish API

Until then, keep the prompt agent. Do not add a hosted-agent image, `azure.yaml` hosted service, or Microsoft 365 Agents SDK project in this repo.

## References

- [Hosted agents in Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Publish to Microsoft 365 and Teams (portal)](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/publish-copilot)
- [Publish to Microsoft 365 and Teams (REST)](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/publish-copilot-virtual-network)
- v1 Teams runbook: [docs/teams.md](teams.md)
