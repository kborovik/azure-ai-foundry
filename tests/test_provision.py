from __future__ import annotations

from pathlib import Path

import pytest

from talos.constants import SEARCH_API_VERSION
from talos.errors import TalosError
from talos.provision import (
    DeployConfig,
    activity_protocol_enabled,
    extract_indexer_name,
    knowledge_source_body,
    resource_id_connection_string,
    run_deploy,
    synchronization_counts,
)
from tests.fakes import FakeAgents, FakeBlobStore, FakeClock, FakeRest, json_response

pytestmark = pytest.mark.unit

SEARCH = "https://srch-cp-demo.search.windows.net"
PROJECT = "https://aif-cp-demo.services.ai.azure.com/api/projects/credit-policy-demo"
PROJECT_ID = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-demo"
    "/providers/Microsoft.CognitiveServices/accounts/aif-cp-demo/projects/credit-policy-demo"
)
STORAGE_ID = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-demo"
    "/providers/Microsoft.Storage/storageAccounts/stcpdemo"
)
AI_SERVICES = "https://aif-cp-demo.services.ai.azure.com"


def _config(tmp_path: Path, **overrides: object) -> DeployConfig:
    instructions = tmp_path / "instructions.md"
    instructions.write_text("You are the credit policy assistant.", encoding="utf-8")
    values = dict(
        search_endpoint=SEARCH,
        project_endpoint=PROJECT,
        project_resource_id=PROJECT_ID,
        storage_resource_id=STORAGE_ID,
        ai_services_endpoint=AI_SERVICES,
        instructions_path=instructions,
        wait_timeout_seconds=30.0,
        poll_interval_seconds=10.0,
        connection_retries=3,
        connection_retry_delay_seconds=1.0,
        min_indexed_items=12,
        min_application_indexed_items=3,
        policy_dir=tmp_path / "policies",
        application_dir=tmp_path / "apps",
    )
    values.update(overrides)
    policy_dir = Path(values["policy_dir"])  # type: ignore[arg-type]
    application_dir = Path(values["application_dir"])  # type: ignore[arg-type]
    policy_dir.mkdir(parents=True, exist_ok=True)
    application_dir.mkdir(parents=True, exist_ok=True)
    if not any(policy_dir.glob("*.md")):
        for index in range(12):
            (policy_dir / f"policy-{index:02d}.md").write_text(
                "SYNTHETIC — DEMO ONLY\n\n# policy\n", encoding="utf-8"
            )
    if not any(application_dir.glob("*.md")):
        for kind in ("accepted", "rejected", "missing-data"):
            (application_dir / f"{kind}.md").write_text(
                "SYNTHETIC — DEMO ONLY\n\n# application\n", encoding="utf-8"
            )
    return DeployConfig(**values)  # type: ignore[arg-type]


def _stores() -> dict[str, FakeBlobStore]:
    return {
        "credit-policies": FakeBlobStore(container="credit-policies"),
        "client-applications": FakeBlobStore(container="client-applications"),
    }


def do_deploy(config: DeployConfig, rest: FakeRest, **kwargs: object) -> None:
    kwargs.setdefault("blob_stores", _stores())
    kwargs.setdefault("clock", FakeClock())
    kwargs.setdefault("echo", lambda _: None)
    if "agents" not in kwargs:
        kwargs["agents"] = FakeAgents()
    _run = run_deploy
    _run(config, rest=rest, **kwargs)  # type: ignore[arg-type]


def _ks_get_body(
    indexer: str = "ks-credit-policies-indexer",
    index: str = "idx-credit-policies",
) -> dict:
    return {
        "name": "ks-credit-policies",
        "azureBlobParameters": {
            "createdResources": {"indexer": indexer, "index": index}
        },
    }


def _script_index_count(
    rest: FakeRest, source_name: str, index_name: str, count: int
) -> None:
    rest.expect(
        "GET",
        f"/knowledgesources/{source_name}?",
        json_response(
            200,
            _ks_get_body(
                indexer=f"{source_name}-indexer",
                index=index_name,
            ),
        ),
    )
    rest.expect(
        "GET",
        f"/indexes/{index_name}/docs/$count",
        json_response(200, count),
    )


def _script_app_source(rest: FakeRest, *, run: bool = True) -> None:
    rest.expect(
        "PUT", "/knowledgesources/ks-client-applications", json_response(201, {})
    )
    rest.expect(
        "GET",
        "/knowledgesources/ks-client-applications?",
        json_response(200, _ks_get_body("ks-client-applications-indexer")),
    )
    if run:
        rest.expect(
            "POST",
            "/indexers/ks-client-applications-indexer/run",
            json_response(202, None),
        )


def _script_source(
    rest: FakeRest,
    *,
    name: str,
    indexer: str,
    wait: bool = False,
    indexer_status: dict | None = None,
    processed: int = 12,
) -> None:
    rest.expect("PUT", f"/knowledgesources/{name}", json_response(201, {"name": name}))
    rest.expect(
        "GET",
        f"/knowledgesources/{name}?",
        json_response(
            200,
            {
                "name": name,
                "azureBlobParameters": {"createdResources": {"indexer": indexer}},
            },
        ),
    )
    rest.expect("POST", f"/indexers/{indexer}/run", json_response(202, None))
    if wait:
        rest.expect(
            "GET",
            f"/knowledgesources/{name}/status",
            json_response(
                200, indexer_status or _done_status(processed=processed, failed=0)
            ),
        )


def _script_happy_path(
    rest: FakeRest,
    *,
    wait: bool = False,
    indexer_status: dict | None = None,
    application_status: dict | None = None,
) -> FakeRest:
    _script_source(
        rest,
        name="ks-credit-policies",
        indexer="ks-credit-policies-indexer",
        wait=wait,
        indexer_status=indexer_status,
        processed=12,
    )
    _script_source(
        rest,
        name="ks-client-applications",
        indexer="ks-client-applications-indexer",
        wait=wait,
        indexer_status=application_status,
        processed=3,
    )
    rest.expect(
        "PUT",
        "/knowledgebases/kb-credit-policies",
        json_response(201, {"name": "kb-credit-policies"}),
    )
    rest.expect(
        "PUT",
        "/connections/conn-kb-credit-policies",
        json_response(200, {"name": "conn-kb-credit-policies"}),
    )
    return rest


def _done_status(*, processed: int, failed: int) -> dict:
    return {
        "kind": "azureBlob",
        "lastSynchronizationState": {
            "endTime": "2026-09-12T18:00:00Z",
            "itemUpdatesProcessed": processed,
            "itemsUpdatesFailed": failed,
        },
    }


def test_resource_id_has_no_trailing_semicolon_by_default() -> None:
    value = resource_id_connection_string(STORAGE_ID, trailing_semicolon=False)
    assert value == f"ResourceId={STORAGE_ID}"
    assert not value.endswith(";")
    assert resource_id_connection_string(STORAGE_ID, trailing_semicolon=True).endswith(
        ";"
    )


def test_knowledge_source_body_uses_extractive_pins() -> None:
    config = DeployConfig(
        search_endpoint=SEARCH,
        project_endpoint=PROJECT,
        project_resource_id=PROJECT_ID,
        storage_resource_id=STORAGE_ID,
        ai_services_endpoint=AI_SERVICES,
    )
    body = knowledge_source_body(config, f"ResourceId={STORAGE_ID}")
    ingestion = body["azureBlobParameters"]["ingestionParameters"]
    assert ingestion["contentExtractionMode"] == "minimal"
    assert ingestion["disableImageVerbalization"] is True
    assert (
        ingestion["embeddingModel"]["azureOpenAIParameters"]["resourceUri"]
        == AI_SERVICES
    )


def test_extract_indexer_name() -> None:
    assert (
        extract_indexer_name(_ks_get_body("ks-credit-policies-indexer"))
        == "ks-credit-policies-indexer"
    )
    assert extract_indexer_name({"name": "ks"}) is None


def test_synchronization_counts_read_both_item_spellings() -> None:
    end, processed, failed = synchronization_counts(
        {
            "lastSynchronizationState": {
                "endTime": "2026-09-12T18:00:00Z",
                "itemsUpdatesProcessed": 12,
                "itemUpdatesFailed": 0,
            }
        }
    )
    assert end is not None
    assert processed == 12
    assert failed == 0


def test_activity_protocol_enabled() -> None:
    assert activity_protocol_enabled(
        {"agent_endpoint": {"protocol_configuration": {"activity": {}}}}
    )
    assert activity_protocol_enabled(
        {"agent_endpoint": {"protocols": ["responses", "activity"]}}
    )
    assert not activity_protocol_enabled(
        {"agent_endpoint": {"protocol_configuration": {"responses": {}}}}
    )


def test_dry_run_makes_no_rest_calls(tmp_path: Path) -> None:
    rest = FakeRest()
    agents = FakeAgents()
    logs: list[str] = []
    do_deploy(
        _config(tmp_path, dry_run=True), rest=rest, agents=agents, echo=logs.append
    )
    assert rest.calls == []
    assert agents.created is None
    assert any("dry-run" in line for line in logs)


def test_happy_path_pins_version_when_activity_not_enabled(tmp_path: Path) -> None:
    rest = _script_happy_path(FakeRest())
    agents = FakeAgents(version="4", agent={"agent_endpoint": {}})
    logs: list[str] = []
    do_deploy(
        _config(tmp_path), rest=rest, agents=agents, clock=FakeClock(), echo=logs.append
    )
    assert agents.created is not None
    assert agents.created["connection_name"] == "conn-kb-credit-policies"
    assert (
        agents.created["mcp_url"]
        == f"{SEARCH}/knowledgebases/kb-credit-policies/mcp?api-version={SEARCH_API_VERSION}"
    )
    assert agents.pinned == ("credit-policy-agent", "4")
    assert rest.pending == 0


def test_skip_indexer_run(tmp_path: Path) -> None:
    rest = FakeRest()
    rest.expect("PUT", "/knowledgesources/ks-credit-policies", json_response(201, {}))
    rest.expect(
        "GET",
        "/knowledgesources/ks-credit-policies?",
        json_response(200, _ks_get_body()),
    )
    _script_app_source(rest, run=False)
    rest.expect("PUT", "/knowledgebases/kb-credit-policies", json_response(201, {}))
    rest.expect("PUT", "/connections/conn-kb-credit-policies", json_response(200, {}))
    agents = FakeAgents()
    do_deploy(
        _config(tmp_path, skip_indexer_run=True),
        rest=rest,
        agents=agents,
        clock=FakeClock(),
        echo=lambda _: None,
    )
    assert not any("/indexers/" in call.url for call in rest.calls)


def test_knowledge_source_retries_trailing_semicolon_on_400(tmp_path: Path) -> None:
    rest = FakeRest()
    rest.expect(
        "PUT",
        "/knowledgesources/ks-credit-policies",
        json_response(400, {"error": {"message": "bad connection"}}),
    )
    rest.expect("PUT", "/knowledgesources/ks-credit-policies", json_response(201, {}))
    rest.expect(
        "GET",
        "/knowledgesources/ks-credit-policies?",
        json_response(200, _ks_get_body()),
    )
    rest.expect(
        "POST", "/indexers/ks-credit-policies-indexer/run", json_response(202, None)
    )
    _script_app_source(rest)
    rest.expect("PUT", "/knowledgebases/kb-credit-policies", json_response(201, {}))
    rest.expect("PUT", "/connections/conn-kb-credit-policies", json_response(200, {}))
    do_deploy(
        _config(tmp_path),
        rest=rest,
        agents=FakeAgents(),
        clock=FakeClock(),
        echo=lambda _: None,
    )
    first, second = rest.calls[0], rest.calls[1]
    assert (
        first.json_body["azureBlobParameters"]["connectionString"]
        == f"ResourceId={STORAGE_ID}"
    )
    assert (
        second.json_body["azureBlobParameters"]["connectionString"]
        == f"ResourceId={STORAGE_ID};"
    )


def test_indexer_409_is_treated_as_already_running(tmp_path: Path) -> None:
    rest = FakeRest()
    rest.expect("PUT", "/knowledgesources/ks-credit-policies", json_response(201, {}))
    rest.expect(
        "GET",
        "/knowledgesources/ks-credit-policies?",
        json_response(200, _ks_get_body()),
    )
    rest.expect(
        "POST",
        "/indexers/ks-credit-policies-indexer/run",
        json_response(409, {"error": {"message": "running"}}),
    )
    _script_app_source(rest)
    rest.expect("PUT", "/knowledgebases/kb-credit-policies", json_response(201, {}))
    rest.expect("PUT", "/connections/conn-kb-credit-policies", json_response(200, {}))
    do_deploy(
        _config(tmp_path),
        rest=rest,
        agents=FakeAgents(),
        clock=FakeClock(),
        echo=lambda _: None,
    )


def test_wait_succeeds_when_processed_and_no_failures(tmp_path: Path) -> None:
    rest = _script_happy_path(FakeRest(), wait=True)
    do_deploy(
        _config(tmp_path, wait=True),
        rest=rest,
        agents=FakeAgents(),
        clock=FakeClock(),
        echo=lambda _: None,
    )


def test_wait_fails_on_failed_item_updates(tmp_path: Path) -> None:
    rest = _script_happy_path(
        FakeRest(),
        wait=True,
        indexer_status=_done_status(processed=12, failed=1),
    )
    with pytest.raises(TalosError, match="failed item updates"):
        do_deploy(
            _config(tmp_path, wait=True),
            rest=rest,
            agents=FakeAgents(),
            clock=FakeClock(),
            echo=lambda _: None,
        )


def test_wait_fails_when_processed_below_minimum(tmp_path: Path) -> None:
    rest = _script_happy_path(
        FakeRest(),
        wait=True,
        indexer_status=_done_status(processed=3, failed=0),
    )
    _script_index_count(rest, "ks-credit-policies", "idx-credit-policies", 2)
    with pytest.raises(TalosError, match="processed 3 items"):
        do_deploy(
            _config(tmp_path, wait=True),
            rest=rest,
            agents=FakeAgents(),
            clock=FakeClock(),
            echo=lambda _: None,
        )


def test_wait_succeeds_when_partial_sync_index_meets_minimum(tmp_path: Path) -> None:
    rest = _script_happy_path(
        FakeRest(),
        wait=True,
        indexer_status=_done_status(processed=1, failed=0),
    )
    _script_index_count(rest, "ks-credit-policies", "idx-credit-policies", 12)
    do_deploy(
        _config(tmp_path, wait=True),
        rest=rest,
        agents=FakeAgents(),
        clock=FakeClock(),
        echo=lambda _: None,
    )


def test_wait_times_out_when_end_time_never_arrives(tmp_path: Path) -> None:
    rest = FakeRest()
    rest.expect("PUT", "/knowledgesources/ks-credit-policies", json_response(201, {}))
    rest.expect(
        "GET",
        "/knowledgesources/ks-credit-policies?",
        json_response(200, _ks_get_body()),
    )
    rest.expect(
        "POST", "/indexers/ks-credit-policies-indexer/run", json_response(202, None)
    )
    _script_app_source(rest)
    pending = json_response(
        200, {"currentSynchronizationState": {"itemUpdatesProcessed": 1}}
    )
    for _ in range(8):
        rest.expect("GET", "/knowledgesources/ks-credit-policies/status", pending)
    with pytest.raises(TalosError, match="timed out"):
        do_deploy(
            _config(
                tmp_path,
                wait=True,
                wait_timeout_seconds=30.0,
                poll_interval_seconds=10.0,
            ),
            rest=rest,
            agents=FakeAgents(),
            clock=FakeClock(),
            echo=lambda _: None,
        )


def test_skip_endpoint_patch_when_activity_enabled(tmp_path: Path) -> None:
    rest = _script_happy_path(FakeRest())
    agents = FakeAgents(
        agent={"agent_endpoint": {"protocol_configuration": {"activity": {}}}}
    )
    do_deploy(
        _config(tmp_path),
        rest=rest,
        agents=agents,
        clock=FakeClock(),
        echo=lambda _: None,
    )
    assert agents.pinned is None


def test_skip_endpoint_patch_flag(tmp_path: Path) -> None:
    rest = _script_happy_path(FakeRest())
    agents = FakeAgents(agent={"agent_endpoint": {}})
    do_deploy(
        _config(tmp_path, skip_endpoint_patch=True),
        rest=rest,
        agents=agents,
        clock=FakeClock(),
        echo=lambda _: None,
    )
    assert agents.pinned is None


def test_project_connection_retries_403(tmp_path: Path) -> None:
    rest = FakeRest()
    rest.expect("PUT", "/knowledgesources/ks-credit-policies", json_response(201, {}))
    rest.expect(
        "GET",
        "/knowledgesources/ks-credit-policies?",
        json_response(200, _ks_get_body()),
    )
    rest.expect(
        "POST", "/indexers/ks-credit-policies-indexer/run", json_response(202, None)
    )
    _script_app_source(rest)
    rest.expect("PUT", "/knowledgebases/kb-credit-policies", json_response(201, {}))
    rest.expect(
        "PUT",
        "/connections/conn-kb-credit-policies",
        json_response(403, {"error": {"message": "RBAC"}}),
    )
    rest.expect("PUT", "/connections/conn-kb-credit-policies", json_response(200, {}))
    clock = FakeClock()
    do_deploy(
        _config(tmp_path),
        rest=rest,
        agents=FakeAgents(),
        clock=clock,
        echo=lambda _: None,
    )
    assert clock.sleeps
    connection_puts = [call for call in rest.calls if "/connections/" in call.url]
    assert len(connection_puts) == 2


def test_knowledge_base_payload_uses_extractive_data(tmp_path: Path) -> None:
    rest = _script_happy_path(FakeRest())
    do_deploy(
        _config(tmp_path),
        rest=rest,
        agents=FakeAgents(),
        clock=FakeClock(),
        echo=lambda _: None,
    )
    kb_put = next(call for call in rest.calls if "/knowledgebases/" in call.url)
    assert kb_put.json_body["outputMode"] == "extractiveData"
    assert kb_put.json_body["retrievalReasoningEffort"] == {"kind": "low"}
    assert kb_put.json_body["knowledgeSources"] == [
        {"name": "ks-credit-policies"},
        {"name": "ks-client-applications"},
    ]


def test_missing_instructions_file_fails(tmp_path: Path) -> None:
    rest = _script_happy_path(FakeRest())
    missing = tmp_path / "nope.md"
    with pytest.raises(TalosError, match="instructions file not found"):
        do_deploy(
            _config(tmp_path, instructions_path=missing),
            rest=rest,
            agents=FakeAgents(),
            clock=FakeClock(),
            echo=lambda _: None,
        )


def test_wait_accepts_index_count_when_last_sync_processed_zero(tmp_path: Path) -> None:
    rest = FakeRest()
    _script_source(
        rest,
        name="ks-credit-policies",
        indexer="ks-credit-policies-indexer",
        wait=True,
        indexer_status=_done_status(processed=0, failed=0),
        processed=0,
    )
    rest.expect(
        "GET",
        "/knowledgesources/ks-credit-policies?",
        json_response(
            200,
            {
                "azureBlobParameters": {
                    "createdResources": {
                        "indexer": "ks-credit-policies-indexer",
                        "index": "ks-credit-policies-index",
                    }
                }
            },
        ),
    )
    rest.expect(
        "GET",
        "/indexes/ks-credit-policies-index/docs/$count",
        json_response(200, 12),
    )
    _script_source(
        rest,
        name="ks-client-applications",
        indexer="ks-client-applications-indexer",
        wait=True,
        indexer_status=_done_status(processed=0, failed=0),
        processed=0,
    )
    rest.expect(
        "GET",
        "/knowledgesources/ks-client-applications?",
        json_response(
            200,
            {
                "azureBlobParameters": {
                    "createdResources": {
                        "indexer": "ks-client-applications-indexer",
                        "index": "ks-client-applications-index",
                    }
                }
            },
        ),
    )
    rest.expect(
        "GET",
        "/indexes/ks-client-applications-index/docs/$count",
        json_response(200, 3),
    )
    rest.expect("PUT", "/knowledgebases/kb-credit-policies", json_response(201, {}))
    rest.expect("PUT", "/connections/conn-kb-credit-policies", json_response(200, {}))
    do_deploy(
        _config(tmp_path, wait=True),
        rest=rest,
        agents=FakeAgents(),
        clock=FakeClock(),
        echo=lambda _: None,
    )


def test_wait_fails_when_application_processed_below_minimum(tmp_path: Path) -> None:
    rest = _script_happy_path(
        FakeRest(),
        wait=True,
        application_status=_done_status(processed=1, failed=0),
    )
    _script_index_count(
        rest, "ks-client-applications", "idx-client-applications", 1
    )
    with pytest.raises(TalosError, match="ks-client-applications"):
        do_deploy(
            _config(tmp_path, wait=True),
            rest=rest,
            agents=FakeAgents(),
            clock=FakeClock(),
            echo=lambda _: None,
        )


def test_wait_fails_when_local_application_corpus_short(tmp_path: Path) -> None:
    config = _config(tmp_path, wait=True)
    for path in Path(config.application_dir).glob("*.md"):
        path.unlink()
    with pytest.raises(TalosError, match="markdown files"):
        do_deploy(
            config,
            rest=FakeRest(),
            agents=FakeAgents(),
            clock=FakeClock(),
            echo=lambda _: None,
        )


def test_deploy_blob_syncs_both_corpora_and_hash_skips(tmp_path: Path) -> None:
    policy_dir = tmp_path / "policies"
    app_dir = tmp_path / "apps"
    policy_dir.mkdir(parents=True)
    app_dir.mkdir(parents=True)
    (policy_dir / "CP-RML-2026-01-residential-mortgage.md").write_text(
        "SYNTHETIC — DEMO ONLY\n\npolicy\n", encoding="utf-8"
    )
    (app_dir / "accepted.md").write_text(
        "SYNTHETIC — DEMO ONLY\n\napp\n", encoding="utf-8"
    )
    stores = _stores()
    rest = _script_happy_path(FakeRest())
    config = _config(tmp_path, policy_dir=policy_dir, application_dir=app_dir)
    do_deploy(config, rest=rest, blob_stores=stores, echo=lambda _: None)
    assert "CP-RML-2026-01-residential-mortgage.md" in stores["credit-policies"].uploads
    assert "accepted.md" in stores["client-applications"].uploads
    stores["credit-policies"].uploads.clear()
    stores["client-applications"].uploads.clear()
    rest2 = _script_happy_path(FakeRest())
    do_deploy(config, rest=rest2, blob_stores=stores, echo=lambda _: None)
    assert stores["credit-policies"].uploads == []
    assert stores["client-applications"].uploads == []


def test_provision_pins_temperature_zero_and_merge_patch() -> None:
    from talos.env import repo_root as find_root

    text = (find_root() / "src/talos/provision.py").read_text(encoding="utf-8")
    assert 'startswith("gpt-5")' in text
    assert 'definition_kwargs["temperature"] = 0' in text
    assert 'content_type="application/merge-patch+json"' in text
    assert "version_selector" in text
    assert "DEFAULT_APPLICATION_KNOWLEDGE_SOURCE" in text
