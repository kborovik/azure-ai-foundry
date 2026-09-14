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
    DEFAULT_APPLICATION_CONTAINER,
    DEFAULT_APPLICATION_KNOWLEDGE_SOURCE,
    DEFAULT_APPLICATION_OUTPUT_RELATIVE,
    DEFAULT_CHAT_DEPLOYMENT,
    DEFAULT_CONNECTION_NAME,
    DEFAULT_CONTAINER,
    DEFAULT_EMBEDDING_DEPLOYMENT,
    DEFAULT_INSTRUCTIONS_RELATIVE,
    DEFAULT_KNOWLEDGE_BASE,
    DEFAULT_KNOWLEDGE_SOURCE,
    DEFAULT_OUTPUT_RELATIVE,
    FOUNDRY_API_VERSION,
    FOUNDRY_SCOPE,
    INDEXER_NAME_RETRIES,
    INDEXER_NAME_RETRY_DELAY_SECONDS,
    KB_DESCRIPTION,
    KB_RETRIEVAL_INSTRUCTIONS,
    KS_APPLICATION_DESCRIPTION,
    KS_DESCRIPTION,
    MIN_APPLICATION_INDEXED_ITEMS,
    MIN_INDEXED_ITEMS,
    POLL_INTERVAL_SECONDS,
    SEARCH_API_VERSION,
    SEARCH_SCOPE,
    WAIT_TIMEOUT_SECONDS,
)
from talos.application import seed_application_fixtures
from talos.env import repo_root
from talos.errors import TalosError
from talos.generate import BlobStore, open_blob_store, sync_markdown_directory
from talos.rest import Clock, RestClient, RestResponse, SystemClock, raise_for_status


Echo = Callable[[str], None]


@dataclass(frozen=True)
class BlobKnowledgeSource:
    name: str
    container: str
    description: str
    local_dir: Path
    min_indexed_items: int


@dataclass(frozen=True)
class DeployConfig:
    search_endpoint: str
    project_endpoint: str
    project_resource_id: str
    storage_resource_id: str
    ai_services_endpoint: str
    storage_account_url: str = ""
    storage_connection_string: str = ""
    container: str = DEFAULT_CONTAINER
    application_container: str = DEFAULT_APPLICATION_CONTAINER
    knowledge_source: str = DEFAULT_KNOWLEDGE_SOURCE
    application_knowledge_source: str = DEFAULT_APPLICATION_KNOWLEDGE_SOURCE
    knowledge_base: str = DEFAULT_KNOWLEDGE_BASE
    agent_name: str = DEFAULT_AGENT_NAME
    connection_name: str = DEFAULT_CONNECTION_NAME
    chat_deployment: str = DEFAULT_CHAT_DEPLOYMENT
    embedding_deployment: str = DEFAULT_EMBEDDING_DEPLOYMENT
    instructions_path: Path | None = None
    policy_dir: Path | None = None
    application_dir: Path | None = None
    application_fixtures_dir: Path | None = None
    wait: bool = False
    skip_indexer_run: bool = False
    skip_endpoint_patch: bool = False
    dry_run: bool = False
    min_indexed_items: int = MIN_INDEXED_ITEMS
    min_application_indexed_items: int = MIN_APPLICATION_INDEXED_ITEMS
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
            # gpt-5* stored definitions reject temperature on invoke.
            definition_kwargs: dict[str, Any] = {
                "model": model,
                "instructions": instructions,
                "tools": [mcp],
            }
            if not str(model).startswith("gpt-5"):
                definition_kwargs["temperature"] = 0
            agent = client.agents.create_version(
                agent_name=agent_name,
                definition=PromptAgentDefinition(**definition_kwargs),
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
    config: DeployConfig,
    connection_string: str,
    *,
    name: str | None = None,
    container: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name or config.knowledge_source,
        "kind": "azureBlob",
        "description": description or KS_DESCRIPTION,
        "azureBlobParameters": {
            "connectionString": connection_string,
            "containerName": container or config.container,
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
        "knowledgeSources": [
            {"name": config.knowledge_source},
            {"name": config.application_knowledge_source},
        ],
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


def local_corpus_size(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return len(list(directory.glob("*.md")))


def deploy_sources(
    config: DeployConfig,
) -> tuple[BlobKnowledgeSource, BlobKnowledgeSource]:
    root = repo_root()
    policy_dir = config.policy_dir or (root / DEFAULT_OUTPUT_RELATIVE)
    application_dir = config.application_dir or (
        root / DEFAULT_APPLICATION_OUTPUT_RELATIVE
    )
    return (
        BlobKnowledgeSource(
            name=config.knowledge_source,
            container=config.container,
            description=KS_DESCRIPTION,
            local_dir=policy_dir,
            min_indexed_items=config.min_indexed_items,
        ),
        BlobKnowledgeSource(
            name=config.application_knowledge_source,
            container=config.application_container,
            description=KS_APPLICATION_DESCRIPTION,
            local_dir=application_dir,
            min_indexed_items=local_corpus_size(application_dir),
        ),
    )


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


def extract_index_name(knowledge_source: dict[str, Any]) -> str | None:
    params = knowledge_source.get("azureBlobParameters") or {}
    created = params.get("createdResources") or {}
    index = created.get("index")
    return str(index) if index else None


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


def synchronization_in_progress(status: dict[str, Any]) -> bool:
    current = status.get("currentSynchronizationState")
    if not isinstance(current, dict) or not current:
        return False
    return not current.get("endTime")


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
    blob_stores: dict[str, BlobStore] | None = None,
    echo: Echo = print,
) -> None:
    fixture_dir = config.application_fixtures_dir
    application_dir = config.application_dir or (
        repo_root() / DEFAULT_APPLICATION_OUTPUT_RELATIVE
    )
    if fixture_dir is not None:
        if config.dry_run:
            echo(f"dry-run: would seed application fixtures from {fixture_dir}")
        else:
            seeded = seed_application_fixtures(application_dir, fixture_dir)
            echo(f"seeded {seeded} application fixture files into {application_dir}")
    sources = deploy_sources(config)
    if config.dry_run:
        _echo_dry_run(config, sources, echo)
        return
    if config.wait:
        _assert_local_wait_ready(sources)

    cred = credential or DefaultAzureCredential()
    rest_client = rest or _require_rest(cred)
    clock = clock or SystemClock()
    agent_ops = agents or SdkAgentOps(rest_client, config.project_endpoint, cred)

    _sync_corpora(config, sources, blob_stores, cred, echo)

    previous_end_times: dict[str, str | None] = {}
    for source in sources:
        echo(f"creating or updating knowledge source '{source.name}'")
        _put_knowledge_source(config, source, rest_client, echo)
        indexer_name = _wait_for_indexer_name(config, source, rest_client, clock, echo)
        echo(f"generated indexer '{indexer_name}'")
        if config.skip_indexer_run:
            echo(f"skipping indexer run for '{source.name}'")
        else:
            if config.wait:
                end_time, _, _ = synchronization_counts(
                    _sync_status(config, source, rest_client)
                )
                previous_end_times[source.name] = end_time
            echo(f"running indexer '{indexer_name}'")
            _run_indexer(config, rest_client, indexer_name)

    if config.wait:
        deadline = clock.monotonic() + config.wait_timeout_seconds
        for source in sources:
            echo(f"waiting for knowledge source '{source.name}' to finish indexing")
            _wait_for_sync(
                config,
                source,
                rest_client,
                clock,
                echo,
                deadline=deadline,
                previous_end_time=previous_end_times.get(source.name),
            )
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


def _echo_dry_run(
    config: DeployConfig,
    sources: tuple[BlobKnowledgeSource, BlobKnowledgeSource],
    echo: Echo,
) -> None:
    connection = resource_id_connection_string(
        config.storage_resource_id, trailing_semicolon=False
    )
    echo("dry-run: would blob-sync local corpora")
    for source in sources:
        echo(f"  {source.local_dir} -> container {source.container}")
    echo("dry-run: would create or update knowledge sources")
    echo(f"  search: {config.search_endpoint}")
    for source in sources:
        echo(f"  knowledge source: {source.name} container: {source.container}")
    echo(f"  connection string: {connection}")
    echo(f"  knowledge base: {config.knowledge_base}")
    echo(
        f"  knowledge sources: {config.knowledge_source}, "
        f"{config.application_knowledge_source}"
    )
    echo(f"  project connection: {config.connection_name}")
    echo(f"  mcp: {mcp_endpoint(config)}")
    echo(f"  agent: {config.agent_name} (model {config.chat_deployment})")
    echo(f"  wait: {config.wait} skip-indexer-run: {config.skip_indexer_run}")


def _sync_corpora(
    config: DeployConfig,
    sources: tuple[BlobKnowledgeSource, BlobKnowledgeSource],
    blob_stores: dict[str, BlobStore] | None,
    credential: TokenCredential,
    echo: Echo,
) -> None:
    env = {
        "AZURE_STORAGE_ACCOUNT_URL": config.storage_account_url,
        "AZURE_STORAGE_CONNECTION_STRING": config.storage_connection_string,
    }
    for source in sources:
        echo(f"blob-sync container '{source.container}' from {source.local_dir}")
        store = (blob_stores or {}).get(source.container)
        if store is None:
            store = open_blob_store(
                env,
                container=source.container,
                account_url=config.storage_account_url,
                credential=credential,
                purpose="deploy",
            )
        sync_markdown_directory(store, source.local_dir, force=False, echo=echo)


def _search_url(config: DeployConfig, path: str) -> str:
    return (
        f"{config.search_endpoint.rstrip('/')}/{path}?api-version={SEARCH_API_VERSION}"
    )


def _put_knowledge_source(
    config: DeployConfig,
    source: BlobKnowledgeSource,
    rest: RestClient,
    echo: Echo,
) -> dict[str, Any]:
    url = _search_url(config, f"knowledgesources/{quote(source.name, safe='')}")
    first = resource_id_connection_string(
        config.storage_resource_id, trailing_semicolon=False
    )
    body_kwargs = {
        "name": source.name,
        "container": source.container,
        "description": source.description,
    }
    response = rest.request(
        "PUT",
        url,
        scope=SEARCH_SCOPE,
        json_body=knowledge_source_body(config, first, **body_kwargs),
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
            json_body=knowledge_source_body(config, retry, **body_kwargs),
            timeout=120.0,
        )
    raise_for_status(response, f"create or update knowledge source '{source.name}'")
    return response.json if isinstance(response.json, dict) else {}


def _wait_for_indexer_name(
    config: DeployConfig,
    source: BlobKnowledgeSource,
    rest: RestClient,
    clock: Clock,
    echo: Echo,
) -> str:
    url = _search_url(config, f"knowledgesources/{quote(source.name, safe='')}")
    last: dict[str, Any] = {}
    for attempt in range(INDEXER_NAME_RETRIES):
        response = rest.request("GET", url, scope=SEARCH_SCOPE)
        raise_for_status(response, f"GET knowledge source '{source.name}'")
        if isinstance(response.json, dict):
            last = response.json
            indexer = extract_indexer_name(last)
            if indexer:
                return indexer
        if attempt + 1 < INDEXER_NAME_RETRIES:
            echo("generated indexer name not ready; retrying")
            clock.sleep(INDEXER_NAME_RETRY_DELAY_SECONDS)
    raise TalosError(
        f"knowledge source '{source.name}' did not report createdResources.indexer"
    )


def _run_indexer(config: DeployConfig, rest: RestClient, indexer_name: str) -> None:
    url = _search_url(config, f"indexers/{quote(indexer_name, safe='')}/run")
    response = rest.request("POST", url, scope=SEARCH_SCOPE)
    if response.status_code == 409:
        return
    raise_for_status(response, f"run indexer '{indexer_name}'")


def _assert_local_wait_ready(
    sources: tuple[BlobKnowledgeSource, BlobKnowledgeSource],
) -> None:
    for source in sources:
        count = len(list(source.local_dir.glob("*.md")))
        if count < source.min_indexed_items:
            raise TalosError(
                f"local {source.local_dir} has {count} markdown files; "
                f"--wait needs at least {source.min_indexed_items}. "
                "Run `uv run talos generate application --all --local-only` "
                "for the application corpus."
            )


def _sync_status(
    config: DeployConfig, source: BlobKnowledgeSource, rest: RestClient
) -> dict[str, Any]:
    url = _search_url(config, f"knowledgesources/{quote(source.name, safe='')}/status")
    response = rest.request("GET", url, scope=SEARCH_SCOPE)
    raise_for_status(response, f"GET knowledge source '{source.name}' status")
    return response.json if isinstance(response.json, dict) else {}


def _wait_for_sync(
    config: DeployConfig,
    source: BlobKnowledgeSource,
    rest: RestClient,
    clock: Clock,
    echo: Echo,
    *,
    deadline: float | None = None,
    previous_end_time: str | None = None,
) -> None:
    if deadline is None:
        deadline = clock.monotonic() + config.wait_timeout_seconds
    while True:
        status = _sync_status(config, source, rest)
        end_time, processed, failed = synchronization_counts(status)
        echo(
            f"{source.name} indexer status: processed={processed} failed={failed} "
            f"endTime={end_time or 'pending'}"
        )
        _echo_status_errors(status, echo)
        awaiting_new_run = synchronization_in_progress(status) or (
            previous_end_time is not None and end_time == previous_end_time
        )
        if awaiting_new_run:
            if clock.monotonic() >= deadline:
                raise TalosError(
                    f"timed out waiting for knowledge source '{source.name}' "
                    f"after {int(config.wait_timeout_seconds)}s"
                )
            clock.sleep(config.poll_interval_seconds)
            continue
        if end_time:
            if failed:
                raise TalosError(
                    f"knowledge source '{source.name}' finished with {failed} failed item updates"
                )
            if processed >= source.min_indexed_items:
                return
            counted = _index_document_count(config, source, rest)
            if counted is not None and counted >= source.min_indexed_items:
                echo(
                    f"{source.name} last sync processed {processed}; "
                    f"index document count {counted} meets minimum {source.min_indexed_items}"
                )
                return
            raise TalosError(
                f"knowledge source '{source.name}' processed {processed} items; "
                f"expected at least {source.min_indexed_items}"
            )
        if clock.monotonic() >= deadline:
            raise TalosError(
                f"timed out waiting for knowledge source '{source.name}' "
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


def _index_document_count(
    config: DeployConfig,
    source: BlobKnowledgeSource,
    rest: RestClient,
) -> int | None:
    ks_url = _search_url(config, f"knowledgesources/{quote(source.name, safe='')}")
    response = rest.request("GET", ks_url, scope=SEARCH_SCOPE)
    if not response.ok or not isinstance(response.json, dict):
        return None
    index_name = extract_index_name(response.json)
    if not index_name:
        return None
    count_url = _search_url(config, f"indexes/{quote(index_name, safe='')}/docs/$count")
    counted = rest.request("GET", count_url, scope=SEARCH_SCOPE)
    if not counted.ok:
        return None
    if isinstance(counted.json, int):
        return counted.json
    text = (counted.text or "").strip()
    if text.isdigit():
        return int(text)
    return None


def _first_int(data: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        return int(value)
    return 0
