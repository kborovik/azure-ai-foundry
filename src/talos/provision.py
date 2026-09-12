from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential

from talos.constants import (
    ARM_API_VERSION,
    ARM_SCOPE,
    CONNECTION_RETRIES,
    CONNECTION_RETRY_DELAY_SECONDS,
    DEFAULT_AGENT_NAME,
    DEFAULT_CHAT_DEPLOYMENT,
    DEFAULT_CONNECTION_NAME,
    DEFAULT_CONTAINER,
    DEFAULT_EMBEDDING_DEPLOYMENT,
    DEFAULT_INSTRUCTIONS_RELATIVE,
    DEFAULT_KNOWLEDGE_BASE,
    DEFAULT_KNOWLEDGE_SOURCE,
    FOUNDRY_API_VERSION,
    FOUNDRY_SCOPE,
    INDEXER_NAME_RETRIES,
    INDEXER_NAME_RETRY_DELAY_SECONDS,
    KB_DESCRIPTION,
    KB_RETRIEVAL_INSTRUCTIONS,
    KS_DESCRIPTION,
    MIN_INDEXED_ITEMS,
    POLL_INTERVAL_SECONDS,
    SEARCH_API_VERSION,
    SEARCH_SCOPE,
    WAIT_TIMEOUT_SECONDS,
)
from talos.env import repo_root
from talos.errors import TalosError
from talos.rest import Clock, RestClient, RestResponse, SystemClock, raise_for_status


Echo = Callable[[str], None]


@dataclass(frozen=True)
class DeployConfig:
    search_endpoint: str
    project_endpoint: str
    project_resource_id: str
    storage_resource_id: str
    ai_services_endpoint: str
    container: str = DEFAULT_CONTAINER
    knowledge_source: str = DEFAULT_KNOWLEDGE_SOURCE
    knowledge_base: str = DEFAULT_KNOWLEDGE_BASE
    agent_name: str = DEFAULT_AGENT_NAME
    connection_name: str = DEFAULT_CONNECTION_NAME
    chat_deployment: str = DEFAULT_CHAT_DEPLOYMENT
    embedding_deployment: str = DEFAULT_EMBEDDING_DEPLOYMENT
    instructions_path: Path | None = None
    wait: bool = False
    skip_indexer_run: bool = False
    skip_endpoint_patch: bool = False
    dry_run: bool = False
    min_indexed_items: int = MIN_INDEXED_ITEMS
    wait_timeout_seconds: float = WAIT_TIMEOUT_SECONDS
    poll_interval_seconds: float = POLL_INTERVAL_SECONDS
    connection_retries: int = CONNECTION_RETRIES
    connection_retry_delay_seconds: float = CONNECTION_RETRY_DELAY_SECONDS


class AgentOps(Protocol):
    def create_version(
        self,
        *,
        agent_name: str,
        model: str,
        instructions: str,
        mcp_url: str,
        connection_name: str,
    ) -> str: ...

    def get_agent(self, agent_name: str) -> dict[str, Any]: ...

    def pin_version(self, agent_name: str, version: str) -> None: ...


class SdkAgentOps:
    def __init__(
        self,
        rest: RestClient,
        project_endpoint: str,
        credential: TokenCredential,
    ) -> None:
        self._rest = rest
        self._project_endpoint = project_endpoint.rstrip("/")
        self._credential = credential

    def create_version(
        self,
        *,
        agent_name: str,
        model: str,
        instructions: str,
        mcp_url: str,
        connection_name: str,
    ) -> str:
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import MCPTool, PromptAgentDefinition

        with AIProjectClient(
            endpoint=self._project_endpoint,
            credential=self._credential,
        ) as client:
            mcp = MCPTool(
                server_label="knowledge-base",
                server_url=mcp_url,
                require_approval="never",
                allowed_tools=["knowledge_base_retrieve"],
                project_connection_id=connection_name,
            )
            agent = client.agents.create_version(
                agent_name=agent_name,
                definition=PromptAgentDefinition(
                    model=model,
                    instructions=instructions,
                    tools=[mcp],
                    temperature=0,
                ),
            )
        version = getattr(agent, "version", None)
        if version is None:
            raise TalosError(f"agent '{agent_name}' was created without a version")
        return str(version)

    def get_agent(self, agent_name: str) -> dict[str, Any]:
        url = (
            f"{self._project_endpoint}/agents/{quote(agent_name, safe='')}"
            f"?api-version={FOUNDRY_API_VERSION}"
        )
        response = self._rest.request("GET", url, scope=FOUNDRY_SCOPE)
        raise_for_status(response, f"GET agent '{agent_name}'")
        if not isinstance(response.json, dict):
            raise TalosError(f"GET agent '{agent_name}' returned a non-object body")
        return response.json

    def pin_version(self, agent_name: str, version: str) -> None:
        url = (
            f"{self._project_endpoint}/agents/{quote(agent_name, safe='')}"
            f"?api-version={FOUNDRY_API_VERSION}"
        )
        body = {
            "agent_endpoint": {
                "version_selector": {
                    "version_selection_rules": [
                        {
                            "type": "FixedRatio",
                            "agent_version": str(version),
                            "traffic_percentage": 100,
                        }
                    ]
                }
            }
        }
        response = self._rest.request(
            "PATCH",
            url,
            scope=FOUNDRY_SCOPE,
            json_body=body,
            content_type="application/merge-patch+json",
        )
        raise_for_status(response, f"pin agent '{agent_name}' version {version}")


def resource_id_connection_string(
    storage_resource_id: str, *, trailing_semicolon: bool
) -> str:
    base = f"ResourceId={storage_resource_id}"
    return f"{base};" if trailing_semicolon else base


def knowledge_source_body(
    config: DeployConfig, connection_string: str
) -> dict[str, Any]:
    return {
        "name": config.knowledge_source,
        "kind": "azureBlob",
        "description": KS_DESCRIPTION,
        "azureBlobParameters": {
            "connectionString": connection_string,
            "containerName": config.container,
            "folderPath": None,
            "isADLSGen2": False,
            "ingestionParameters": {
                "embeddingModel": {
                    "kind": "azureOpenAI",
                    "azureOpenAIParameters": {
                        "resourceUri": config.ai_services_endpoint,
                        "deploymentId": config.embedding_deployment,
                        "modelName": config.embedding_deployment,
                    },
                },
                "contentExtractionMode": "minimal",
                "disableImageVerbalization": True,
            },
        },
    }


def knowledge_base_body(config: DeployConfig) -> dict[str, Any]:
    return {
        "name": config.knowledge_base,
        "description": KB_DESCRIPTION,
        "retrievalInstructions": KB_RETRIEVAL_INSTRUCTIONS,
        "knowledgeSources": [{"name": config.knowledge_source}],
        "outputMode": "extractiveData",
        "retrievalReasoningEffort": {"kind": "low"},
        "models": [
            {
                "kind": "azureOpenAI",
                "azureOpenAIParameters": {
                    "resourceUri": config.ai_services_endpoint,
                    "deploymentId": config.chat_deployment,
                    "modelName": config.chat_deployment,
                },
            }
        ],
    }


def mcp_endpoint(config: DeployConfig) -> str:
    search = config.search_endpoint.rstrip("/")
    kb = quote(config.knowledge_base, safe="")
    return f"{search}/knowledgebases/{kb}/mcp?api-version={SEARCH_API_VERSION}"


def project_connection_body(config: DeployConfig) -> dict[str, Any]:
    return {
        "name": config.connection_name,
        "type": "Microsoft.MachineLearningServices/workspaces/connections",
        "properties": {
            "authType": "ProjectManagedIdentity",
            "category": "RemoteTool",
            "target": mcp_endpoint(config),
            "isSharedToAll": True,
            "audience": "https://search.azure.com/",
            "metadata": {"ApiType": "Azure"},
        },
    }


def extract_indexer_name(knowledge_source: dict[str, Any]) -> str | None:
    params = knowledge_source.get("azureBlobParameters") or {}
    created = params.get("createdResources") or {}
    indexer = created.get("indexer")
    return str(indexer) if indexer else None


def synchronization_counts(status: dict[str, Any]) -> tuple[str | None, int, int]:
    state = status.get("lastSynchronizationState")
    if not isinstance(state, dict):
        current = status.get("currentSynchronizationState")
        if isinstance(current, dict):
            processed = _first_int(
                current, "itemUpdatesProcessed", "itemsUpdatesProcessed"
            )
            failed = _first_int(current, "itemsUpdatesFailed", "itemUpdatesFailed")
            return None, processed, failed
        return None, 0, 0
    end_time = state.get("endTime")
    processed = _first_int(state, "itemUpdatesProcessed", "itemsUpdatesProcessed")
    failed = _first_int(state, "itemsUpdatesFailed", "itemUpdatesFailed")
    return (str(end_time) if end_time else None), processed, failed


def activity_protocol_enabled(agent: dict[str, Any]) -> bool:
    endpoint = agent.get("agent_endpoint") or {}
    protocol_configuration = endpoint.get("protocol_configuration") or {}
    if (
        isinstance(protocol_configuration, dict)
        and "activity" in protocol_configuration
    ):
        return True
    protocols = endpoint.get("protocols") or []
    if isinstance(protocols, list):
        return "activity" in protocols
    return False


def load_instructions(path: Path | None) -> str:
    instructions_path = path or (repo_root() / DEFAULT_INSTRUCTIONS_RELATIVE)
    if not instructions_path.is_file():
        raise TalosError(f"agent instructions file not found: {instructions_path}")
    text = instructions_path.read_text(encoding="utf-8").strip()
    if not text:
        raise TalosError(f"agent instructions file is empty: {instructions_path}")
    return text


def run_deploy(
    config: DeployConfig,
    *,
    rest: RestClient | None = None,
    agents: AgentOps | None = None,
    clock: Clock | None = None,
    credential: TokenCredential | None = None,
    echo: Echo = print,
) -> None:
    if config.dry_run:
        _echo_dry_run(config, echo)
        return

    cred = credential or DefaultAzureCredential()
    rest_client = rest or _require_rest(cred)
    clock = clock or SystemClock()
    agent_ops = agents or SdkAgentOps(rest_client, config.project_endpoint, cred)

    echo(f"creating or updating knowledge source '{config.knowledge_source}'")
    _put_knowledge_source(config, rest_client, echo)
    indexer_name = _wait_for_indexer_name(config, rest_client, clock, echo)
    echo(f"generated indexer '{indexer_name}'")

    if config.skip_indexer_run:
        echo("skipping indexer run")
    else:
        echo(f"running indexer '{indexer_name}'")
        _run_indexer(config, rest_client, indexer_name)

    if config.wait:
        echo(
            f"waiting for knowledge source '{config.knowledge_source}' to finish indexing"
        )
        _wait_for_sync(config, rest_client, clock, echo)
    else:
        echo("not waiting for indexer (pass --wait to poll)")

    echo(f"creating or updating knowledge base '{config.knowledge_base}'")
    _put_knowledge_base(config, rest_client)

    echo(f"creating or updating project connection '{config.connection_name}'")
    _put_project_connection(config, rest_client, clock, echo)

    instructions = load_instructions(config.instructions_path)
    echo(f"creating agent version '{config.agent_name}'")
    version = agent_ops.create_version(
        agent_name=config.agent_name,
        model=config.chat_deployment,
        instructions=instructions,
        mcp_url=mcp_endpoint(config),
        connection_name=config.connection_name,
    )
    echo(f"created agent '{config.agent_name}' version {version}")

    agent = agent_ops.get_agent(config.agent_name)
    if config.skip_endpoint_patch or activity_protocol_enabled(agent):
        reason = (
            "--skip-endpoint-patch"
            if config.skip_endpoint_patch
            else "Activity protocol already enabled"
        )
        echo(f"skipping agent endpoint patch ({reason})")
        return

    echo(f"pinning agent '{config.agent_name}' to version {version}")
    agent_ops.pin_version(config.agent_name, version)


def _require_rest(credential: TokenCredential) -> RestClient:
    from talos.rest import RequestsRest

    return RequestsRest(credential)


def _echo_dry_run(config: DeployConfig, echo: Echo) -> None:
    connection = resource_id_connection_string(
        config.storage_resource_id, trailing_semicolon=False
    )
    echo("dry-run: would create or update knowledge source")
    echo(f"  search: {config.search_endpoint}")
    echo(f"  knowledge source: {config.knowledge_source}")
    echo(f"  connection string: {connection}")
    echo(f"  container: {config.container}")
    echo(f"  knowledge base: {config.knowledge_base}")
    echo(f"  project connection: {config.connection_name}")
    echo(f"  mcp: {mcp_endpoint(config)}")
    echo(f"  agent: {config.agent_name} (model {config.chat_deployment})")
    echo(f"  wait: {config.wait} skip-indexer-run: {config.skip_indexer_run}")


def _search_url(config: DeployConfig, path: str) -> str:
    return (
        f"{config.search_endpoint.rstrip('/')}/{path}?api-version={SEARCH_API_VERSION}"
    )


def _put_knowledge_source(
    config: DeployConfig, rest: RestClient, echo: Echo
) -> dict[str, Any]:
    url = _search_url(
        config, f"knowledgesources/{quote(config.knowledge_source, safe='')}"
    )
    first = resource_id_connection_string(
        config.storage_resource_id, trailing_semicolon=False
    )
    response = rest.request(
        "PUT",
        url,
        scope=SEARCH_SCOPE,
        json_body=knowledge_source_body(config, first),
        timeout=120.0,
    )
    if response.status_code == 400:
        echo(
            "knowledge source create returned 400; retrying ResourceId with trailing semicolon"
        )
        retry = resource_id_connection_string(
            config.storage_resource_id, trailing_semicolon=True
        )
        response = rest.request(
            "PUT",
            url,
            scope=SEARCH_SCOPE,
            json_body=knowledge_source_body(config, retry),
            timeout=120.0,
        )
    raise_for_status(
        response, f"create or update knowledge source '{config.knowledge_source}'"
    )
    return response.json if isinstance(response.json, dict) else {}


def _wait_for_indexer_name(
    config: DeployConfig,
    rest: RestClient,
    clock: Clock,
    echo: Echo,
) -> str:
    url = _search_url(
        config, f"knowledgesources/{quote(config.knowledge_source, safe='')}"
    )
    last: dict[str, Any] = {}
    for attempt in range(INDEXER_NAME_RETRIES):
        response = rest.request("GET", url, scope=SEARCH_SCOPE)
        raise_for_status(response, f"GET knowledge source '{config.knowledge_source}'")
        if isinstance(response.json, dict):
            last = response.json
            indexer = extract_indexer_name(last)
            if indexer:
                return indexer
        if attempt + 1 < INDEXER_NAME_RETRIES:
            echo("generated indexer name not ready; retrying")
            clock.sleep(INDEXER_NAME_RETRY_DELAY_SECONDS)
    raise TalosError(
        f"knowledge source '{config.knowledge_source}' did not report createdResources.indexer"
    )


def _run_indexer(config: DeployConfig, rest: RestClient, indexer_name: str) -> None:
    url = _search_url(config, f"indexers/{quote(indexer_name, safe='')}/run")
    response = rest.request("POST", url, scope=SEARCH_SCOPE)
    if response.status_code == 409:
        return
    raise_for_status(response, f"run indexer '{indexer_name}'")


def _wait_for_sync(
    config: DeployConfig,
    rest: RestClient,
    clock: Clock,
    echo: Echo,
) -> None:
    url = _search_url(
        config, f"knowledgesources/{quote(config.knowledge_source, safe='')}/status"
    )
    deadline = clock.monotonic() + config.wait_timeout_seconds
    while True:
        response = rest.request("GET", url, scope=SEARCH_SCOPE)
        raise_for_status(
            response, f"GET knowledge source '{config.knowledge_source}' status"
        )
        status = response.json if isinstance(response.json, dict) else {}
        end_time, processed, failed = synchronization_counts(status)
        echo(
            f"indexer status: processed={processed} failed={failed} endTime={end_time or 'pending'}"
        )
        _echo_status_errors(status, echo)
        if end_time:
            if failed:
                raise TalosError(
                    f"knowledge source '{config.knowledge_source}' finished with {failed} failed item updates"
                )
            if processed < config.min_indexed_items:
                raise TalosError(
                    f"knowledge source '{config.knowledge_source}' processed {processed} items; "
                    f"expected at least {config.min_indexed_items}"
                )
            return
        if clock.monotonic() >= deadline:
            raise TalosError(
                f"timed out waiting for knowledge source '{config.knowledge_source}' "
                f"after {int(config.wait_timeout_seconds)}s"
            )
        clock.sleep(config.poll_interval_seconds)


def _echo_status_errors(status: dict[str, Any], echo: Echo) -> None:
    for key in ("currentSynchronizationState", "lastSynchronizationState"):
        state = status.get(key)
        if not isinstance(state, dict):
            continue
        errors = state.get("errors") or []
        if not isinstance(errors, list):
            continue
        for error in errors[:5]:
            if not isinstance(error, dict):
                continue
            message = str(error.get("errorMessage") or error.get("message") or "")[:500]
            doc = error.get("docURL") or error.get("key") or ""
            echo(f"  indexer error: {message} ({doc})")


def _put_knowledge_base(config: DeployConfig, rest: RestClient) -> None:
    url = _search_url(config, f"knowledgebases/{quote(config.knowledge_base, safe='')}")
    response = rest.request(
        "PUT",
        url,
        scope=SEARCH_SCOPE,
        json_body=knowledge_base_body(config),
        timeout=120.0,
    )
    raise_for_status(
        response, f"create or update knowledge base '{config.knowledge_base}'"
    )


def _put_project_connection(
    config: DeployConfig,
    rest: RestClient,
    clock: Clock,
    echo: Echo,
) -> None:
    url = (
        f"https://management.azure.com{config.project_resource_id}"
        f"/connections/{quote(config.connection_name, safe='')}"
        f"?api-version={ARM_API_VERSION}"
    )
    body = project_connection_body(config)
    last: RestResponse | None = None
    for attempt in range(config.connection_retries):
        last = rest.request("PUT", url, scope=ARM_SCOPE, json_body=body)
        if last.ok:
            return
        if last.status_code == 403 and attempt + 1 < config.connection_retries:
            echo("project connection returned 403; retrying after RBAC propagation")
            clock.sleep(config.connection_retry_delay_seconds)
            continue
        break
    assert last is not None
    raise_for_status(
        last, f"create or update project connection '{config.connection_name}'"
    )


def _first_int(data: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        return int(value)
    return 0
