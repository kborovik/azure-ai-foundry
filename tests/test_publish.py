from __future__ import annotations

import base64
import json

import pytest
from click.testing import CliRunner

from talos.cli import cli
from talos.constants import (
    ACTIVITY_PROTOCOL_API_VERSION,
    BOT_API_VERSION,
    BOT_CHANNEL_API_VERSION,
    PUBLISH_SCOPE_JUST_YOU,
)
from talos.env import repo_root
from talos.errors import TalosError
from talos.publish import (
    PublishConfig,
    activity_protocol_endpoint,
    agent_client_id,
    bot_arm_id,
    bot_service_rbac_enabled,
    needs_publish_endpoint_patch,
    publish_endpoint_patch,
    resource_group_from_resource_id,
    run_publish,
    subscription_id_from_resource_id,
    tenant_from_jwt,
)
from tests.fakes import FakeRest, json_response

pytestmark = pytest.mark.unit

PROJECT = "https://aif-cp-demo.services.ai.azure.com/api/projects/credit-policy-demo"
PROJECT_ID = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-demo"
    "/providers/Microsoft.CognitiveServices/accounts/aif-cp-demo/projects/credit-policy-demo"
)
CLIENT_ID = "00001111-aaaa-2222-bbbb-3333cccc4444"
TENANT = "11112222-3333-4444-5555-666677778888"


def _config(**overrides: object) -> PublishConfig:
    values: dict[str, object] = dict(
        project_endpoint=PROJECT,
        project_resource_id=PROJECT_ID,
        resource_group="rg-demo",
        tenant_id=TENANT,
    )
    values.update(overrides)
    return PublishConfig(**values)  # type: ignore[arg-type]


def _agent(**endpoint: object) -> dict:
    body: dict = {
        "name": "credit-policy-agent",
        "instance_identity": {"client_id": CLIENT_ID},
        "agent_endpoint": dict(endpoint) if endpoint else {},
    }
    return body


def _script_publish(
    rest: FakeRest,
    *,
    agent: dict | None = None,
    patch: bool = True,
    bot: bool = True,
    title_id: str = "title-1",
    publish_status: int = 200,
) -> FakeRest:
    rest.expect(
        "GET", "/agents/credit-policy-agent?", json_response(200, agent or _agent())
    )
    if patch:
        rest.expect(
            "PATCH",
            "/agents/credit-policy-agent?",
            json_response(200, {}),
        )
    if bot:
        rest.expect(
            "PUT", "/botServices/bot-credit-policy-agent?", json_response(201, {})
        )
        rest.expect("PUT", "/channels/MsTeamsChannel", json_response(200, {}))
    rest.expect(
        "POST",
        "/microsoft365/publish",
        json_response(
            publish_status, {"titleId": title_id} if publish_status < 300 else {}
        ),
    )
    return rest


def test_subscription_and_resource_group_parse() -> None:
    assert (
        subscription_id_from_resource_id(PROJECT_ID)
        == "00000000-0000-0000-0000-000000000000"
    )
    assert resource_group_from_resource_id(PROJECT_ID) == "rg-demo"


def test_tenant_from_jwt() -> None:
    payload = (
        base64.urlsafe_b64encode(json.dumps({"tid": TENANT}).encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )
    assert tenant_from_jwt(f"header.{payload}.sig") == TENANT
    assert tenant_from_jwt("not-a-jwt") == ""


def test_agent_client_id_required() -> None:
    with pytest.raises(TalosError, match="instance_identity"):
        agent_client_id({"agent_endpoint": {}})


def test_activity_protocol_endpoint_uses_preview_api() -> None:
    url = activity_protocol_endpoint(PROJECT, "credit-policy-agent")
    assert url.endswith(f"activityProtocol?api-version={ACTIVITY_PROTOCOL_API_VERSION}")
    assert "/agents/credit-policy-agent/endpoint/protocols/activityProtocol" in url


def test_publish_endpoint_patch_keeps_existing_protocols_and_entra() -> None:
    agent = _agent(
        protocol_configuration={"responses": {}, "invocations": {}},
        authorization_schemes=[{"type": "Entra"}],
    )
    body = publish_endpoint_patch(agent)
    protocols = body["agent_endpoint"]["protocol_configuration"]
    schemes = {item["type"] for item in body["agent_endpoint"]["authorization_schemes"]}
    assert "responses" in protocols
    assert "invocations" in protocols
    assert "activity" in protocols
    assert "enable_m365_public_endpoint" not in protocols["activity"]
    assert schemes == {"Entra", "BotServiceRbac"}


def test_needs_patch_false_when_activity_and_rbac_present() -> None:
    agent = _agent(
        protocol_configuration={"responses": {}, "activity": {}},
        authorization_schemes=[{"type": "Entra"}, {"type": "BotServiceRbac"}],
    )
    assert bot_service_rbac_enabled(agent)
    assert not needs_publish_endpoint_patch(agent)


def test_dry_run_makes_no_rest_calls() -> None:
    rest = FakeRest()
    logs: list[str] = []
    run_publish(_config(dry_run=True), rest=rest, echo=logs.append)
    assert rest.calls == []
    joined = "\n".join(logs)
    assert "dry-run" in joined
    assert "Just you" in joined
    assert "BotServiceRbac" in joined
    assert PUBLISH_SCOPE_JUST_YOU in joined
    assert "microsoft365/publish" in joined


def test_happy_path_patches_then_puts_bot_then_publishes_shared() -> None:
    rest = _script_publish(
        FakeRest(), agent=_agent(protocol_configuration={"responses": {}})
    )
    logs: list[str] = []
    run_publish(_config(), rest=rest, echo=logs.append)
    assert rest.pending == 0
    methods = [call.method for call in rest.calls]
    assert methods == ["GET", "PATCH", "PUT", "PUT", "POST"]
    patch = rest.calls[1]
    assert patch.content_type == "application/merge-patch+json"
    protocols = patch.json_body["agent_endpoint"]["protocol_configuration"]
    assert "responses" in protocols
    assert "activity" in protocols
    schemes = [
        item["type"]
        for item in patch.json_body["agent_endpoint"]["authorization_schemes"]
    ]
    assert "Entra" in schemes
    assert "BotServiceRbac" in schemes
    bot = rest.calls[2]
    assert BOT_API_VERSION in bot.url
    assert bot.json_body["properties"]["msaAppId"] == CLIENT_ID
    assert bot.json_body["properties"]["msaAppTenantId"] == TENANT
    assert bot.json_body["properties"]["publicNetworkAccess"] == "Enabled"
    channel = rest.calls[3]
    assert BOT_CHANNEL_API_VERSION in channel.url
    assert "MsTeamsChannel" in channel.url
    publish = rest.calls[4]
    assert publish.json_body["publishScope"] == PUBLISH_SCOPE_JUST_YOU
    assert publish.json_body["publishAsAutopilot"] is False
    assert publish.json_body["appVersion"] == "1.0.0"
    expected_bot = bot_arm_id(
        "00000000-0000-0000-0000-000000000000", "rg-demo", "bot-credit-policy-agent"
    )
    assert publish.json_body["botServiceArmId"] == expected_bot
    assert any("title-1" in line for line in logs)


def test_skips_endpoint_patch_when_activity_and_rbac_already_enabled() -> None:
    agent = _agent(
        protocol_configuration={"responses": {}, "activity": {}},
        authorization_schemes=[{"type": "Entra"}, {"type": "BotServiceRbac"}],
    )
    rest = _script_publish(FakeRest(), agent=agent, patch=False)
    logs: list[str] = []
    run_publish(_config(), rest=rest, echo=logs.append)
    assert rest.pending == 0
    assert not any(call.method == "PATCH" for call in rest.calls)
    assert any("already enabled" in line for line in logs)


def test_bot_arm_id_skips_bot_create() -> None:
    arm = bot_arm_id("00000000-0000-0000-0000-000000000000", "rg-demo", "existing-bot")
    rest = _script_publish(
        FakeRest(),
        agent=_agent(protocol_configuration={"responses": {}}),
        bot=False,
    )
    run_publish(_config(bot_arm_id=arm), rest=rest, echo=lambda _: None)
    assert rest.pending == 0
    assert not any("botServices" in call.url for call in rest.calls)
    publish = rest.calls[-1]
    assert publish.json_body["botServiceArmId"] == arm


def test_publish_409_asks_to_increment_app_version() -> None:
    rest = _script_publish(
        FakeRest(),
        agent=_agent(protocol_configuration={"responses": {}}),
        publish_status=409,
    )
    with pytest.raises(TalosError, match="increment --app-version"):
        run_publish(_config(), rest=rest, echo=lambda _: None)


def test_invalid_app_version_rejected() -> None:
    with pytest.raises(TalosError, match="app version"):
        run_publish(_config(app_version="0.1.0", dry_run=True), echo=lambda _: None)


def test_cli_publish_help_documents_just_you_flags() -> None:
    result = CliRunner().invoke(cli, ["publish", "--help"])
    assert result.exit_code == 0, result.output
    for flag in (
        "--project-endpoint",
        "--dry-run",
        "--no-terraform",
        "--skip-endpoint-patch",
        "--app-version",
        "--bot-arm-id",
    ):
        assert flag in result.output
    assert "Just you" in result.output
    assert "infra/outputs.json" in result.output


def test_cli_publish_missing_env_exits_2(clean_azure_env: None) -> None:
    result = CliRunner().invoke(cli, ["publish", "--no-terraform"])
    assert result.exit_code == 2
    assert "Azure environment is not configured" in result.output


def test_cli_publish_dry_run(clean_azure_env: None) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "publish",
            "--dry-run",
            "--no-terraform",
            "--project-endpoint",
            PROJECT,
            "--project-resource-id",
            PROJECT_ID,
        ],
    )
    assert result.exit_code == 0, result.output
    assert "dry-run" in result.output
    assert "BotServiceRbac" in result.output
    assert PUBLISH_SCOPE_JUST_YOU in result.output
    assert "rg-demo" in result.output


def test_spike_doc_keeps_hosted_agents_out_of_v1() -> None:
    text = (repo_root() / "docs/hosted-agents.md").read_text(encoding="utf-8")
    for needle in (
        "not v1",
        "prompt agent",
        "Microsoft 365 Agents SDK",
        "hosted agents",
        "knowledge_base_retrieve",
        "talos publish",
    ):
        assert needle.lower() in text.lower(), needle
    assert "BotServiceRbac" in text or "Just you" in text
