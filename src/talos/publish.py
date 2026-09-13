from __future__ import annotations

import base64
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential

from talos.constants import (
    ACTIVITY_PROTOCOL_API_VERSION,
    ARM_SCOPE,
    BOT_API_VERSION,
    BOT_CHANNEL_API_VERSION,
    DEFAULT_AGENT_NAME,
    DEFAULT_APP_VERSION,
    DEFAULT_BOT_NAME,
    DEFAULT_DEVELOPER_NAME,
    DEFAULT_PUBLISH_DISPLAY_NAME,
    DEFAULT_PUBLISH_FULL_DESCRIPTION,
    DEFAULT_PUBLISH_SHORT_DESCRIPTION,
    FOUNDRY_API_VERSION,
    FOUNDRY_SCOPE,
    PUBLISH_SCOPE_JUST_YOU,
)
from talos.errors import TalosError
from talos.provision import activity_protocol_enabled
from talos.rest import RestClient, RestResponse, raise_for_status

Echo = Callable[[str], None]
DEVELOPER_NAME_MAX = 32


@dataclass(frozen=True)
class PublishConfig:
    project_endpoint: str
    project_resource_id: str
    resource_group: str
    agent_name: str = DEFAULT_AGENT_NAME
    bot_name: str = DEFAULT_BOT_NAME
    bot_arm_id: str = ""
    display_name: str = DEFAULT_PUBLISH_DISPLAY_NAME
    app_version: str = DEFAULT_APP_VERSION
    developer_name: str = DEFAULT_DEVELOPER_NAME
    short_description: str = DEFAULT_PUBLISH_SHORT_DESCRIPTION
    full_description: str = DEFAULT_PUBLISH_FULL_DESCRIPTION
    tenant_id: str = ""
    dry_run: bool = False
    skip_endpoint_patch: bool = False


def subscription_id_from_resource_id(resource_id: str) -> str:
    parts = resource_id.strip("/").split("/")
    for index, part in enumerate(parts):
        if part.lower() == "subscriptions" and index + 1 < len(parts):
            return parts[index + 1]
    raise TalosError(f"could not parse subscription id from {resource_id}", exit_code=2)


def resource_group_from_resource_id(resource_id: str) -> str:
    parts = resource_id.strip("/").split("/")
    for index, part in enumerate(parts):
        if part.lower() == "resourcegroups" and index + 1 < len(parts):
            return parts[index + 1]
    raise TalosError(f"could not parse resource group from {resource_id}", exit_code=2)


def bot_arm_id(subscription_id: str, resource_group: str, bot_name: str) -> str:
    return (
        f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        f"/providers/Microsoft.BotService/botServices/{bot_name}"
    )


def activity_protocol_endpoint(project_endpoint: str, agent_name: str) -> str:
    base = project_endpoint.rstrip("/")
    name = quote(agent_name, safe="")
    return (
        f"{base}/agents/{name}/endpoint/protocols/activityProtocol"
        f"?api-version={ACTIVITY_PROTOCOL_API_VERSION}"
    )


def tenant_from_jwt(token: str) -> str:
    try:
        payload = token.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except IndexError, ValueError, json.JSONDecodeError:
        return ""
    if not isinstance(data, dict):
        return ""
    tid = data.get("tid")
    return str(tid) if tid else ""


def agent_client_id(agent: dict[str, Any]) -> str:
    identity = agent.get("instance_identity") or {}
    client_id = identity.get("client_id") if isinstance(identity, dict) else None
    if not client_id:
        raise TalosError(
            "agent has no instance_identity.client_id; "
            "cannot create Azure Bot Service for Teams publish"
        )
    return str(client_id)


def bot_service_rbac_enabled(agent: dict[str, Any]) -> bool:
    endpoint = agent.get("agent_endpoint") or {}
    schemes = endpoint.get("authorization_schemes") or []
    if not isinstance(schemes, list):
        return False
    return any(
        isinstance(scheme, dict) and scheme.get("type") == "BotServiceRbac"
        for scheme in schemes
    )


def existing_protocol_configuration(endpoint: dict[str, Any]) -> dict[str, Any]:
    config = endpoint.get("protocol_configuration")
    if isinstance(config, dict) and config:
        return dict(config)
    protocols = endpoint.get("protocols") or []
    if isinstance(protocols, list):
        return {name: {} for name in protocols if isinstance(name, str)}
    return {"responses": {}}


def existing_authorization_schemes(endpoint: dict[str, Any]) -> list[dict[str, Any]]:
    schemes = endpoint.get("authorization_schemes") or []
    if not isinstance(schemes, list):
        return [{"type": "Entra"}]
    copied: list[dict[str, Any]] = [
        dict(scheme) for scheme in schemes if isinstance(scheme, dict)
    ]
    return copied or [{"type": "Entra"}]


def publish_endpoint_patch(agent: dict[str, Any]) -> dict[str, Any]:
    endpoint = agent.get("agent_endpoint") or {}
    if not isinstance(endpoint, dict):
        endpoint = {}
    protocols = existing_protocol_configuration(endpoint)
    if "responses" not in protocols:
        protocols["responses"] = {}
    if "activity" not in protocols:
        protocols["activity"] = {}
    schemes = existing_authorization_schemes(endpoint)
    types = {scheme.get("type") for scheme in schemes}
    if "Entra" not in types:
        schemes.append({"type": "Entra"})
    if "BotServiceRbac" not in types:
        schemes.append({"type": "BotServiceRbac"})
    return {
        "agent_endpoint": {
            "protocol_configuration": protocols,
            "authorization_schemes": schemes,
        }
    }


def needs_publish_endpoint_patch(agent: dict[str, Any]) -> bool:
    return not (activity_protocol_enabled(agent) and bot_service_rbac_enabled(agent))


def bot_service_body(
    *,
    display_name: str,
    endpoint: str,
    client_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    return {
        "location": "global",
        "kind": "azurebot",
        "sku": {"name": "F0"},
        "properties": {
            "displayName": display_name,
            "endpoint": endpoint,
            "msaAppId": client_id,
            "msaAppTenantId": tenant_id,
            "msaAppType": "SingleTenant",
            "publicNetworkAccess": "Enabled",
        },
    }


def teams_channel_body() -> dict[str, Any]:
    return {
        "location": "global",
        "properties": {"channelName": "MsTeamsChannel"},
    }


def publish_body(config: PublishConfig, resolved_bot_arm_id: str) -> dict[str, Any]:
    return {
        "agentDisplayName": config.display_name,
        "botServiceArmId": resolved_bot_arm_id,
        "publishScope": PUBLISH_SCOPE_JUST_YOU,
        "publishAsAutopilot": False,
        "appVersion": config.app_version,
        "shortDescription": config.short_description,
        "fullDescription": config.full_description,
        "developerName": config.developer_name,
    }


def validate_publish_metadata(config: PublishConfig) -> None:
    if len(config.developer_name) > DEVELOPER_NAME_MAX:
        raise TalosError(
            f"developer name cannot exceed {DEVELOPER_NAME_MAX} characters",
            exit_code=1,
        )
    version = config.app_version
    if (
        not version
        or version.startswith("0")
        or any(ch not in "0123456789." for ch in version)
    ):
        raise TalosError(
            "app version must contain only digits and periods and cannot start with 0",
            exit_code=1,
        )


def run_publish(
    config: PublishConfig,
    *,
    rest: RestClient | None = None,
    credential: TokenCredential | None = None,
    echo: Echo = print,
) -> None:
    validate_publish_metadata(config)
    subscription_id = subscription_id_from_resource_id(config.project_resource_id)
    resolved_bot_arm_id = config.bot_arm_id or bot_arm_id(
        subscription_id, config.resource_group, config.bot_name
    )
    if config.dry_run:
        _echo_dry_run(config, subscription_id, resolved_bot_arm_id, echo)
        return

    cred = credential or DefaultAzureCredential()
    rest_client = rest or _require_rest(cred)
    tenant_id = _resolve_tenant_id(config.tenant_id, cred)
    agent = _get_agent(config, rest_client)
    client_id = agent_client_id(agent)

    if config.skip_endpoint_patch or not needs_publish_endpoint_patch(agent):
        reason = (
            "--skip-endpoint-patch"
            if config.skip_endpoint_patch
            else "Activity protocol and BotServiceRbac already enabled"
        )
        echo(f"skipping agent endpoint patch ({reason})")
    else:
        echo(
            f"enabling Activity protocol and BotServiceRbac on '{config.agent_name}' "
            "without dropping existing protocols or schemes"
        )
        _patch_endpoint(config, rest_client, publish_endpoint_patch(agent))

    if config.bot_arm_id:
        echo(f"using existing bot {resolved_bot_arm_id}")
    else:
        echo(f"creating or updating Azure Bot Service '{config.bot_name}'")
        _put_bot(config, rest_client, client_id, tenant_id, resolved_bot_arm_id)
        echo(f"enabling Microsoft Teams channel on '{config.bot_name}'")
        _put_teams_channel(rest_client, resolved_bot_arm_id)

    echo(
        f"publishing '{config.agent_name}' to Microsoft 365/Teams "
        f"(Just you, {PUBLISH_SCOPE_JUST_YOU})"
    )
    _post_publish(config, rest_client, resolved_bot_arm_id, echo)


def _require_rest(credential: TokenCredential) -> RestClient:
    from talos.rest import RequestsRest

    return RequestsRest(credential)


def _resolve_tenant_id(tenant_id: str, credential: TokenCredential) -> str:
    if tenant_id:
        return tenant_id
    token = credential.get_token(FOUNDRY_SCOPE)
    tid = tenant_from_jwt(token.token)
    if not tid:
        raise TalosError(
            "tenant id is required (pass --tenant-id or set AZURE_TENANT_ID)",
            exit_code=2,
        )
    return tid


def _agent_url(config: PublishConfig) -> str:
    name = quote(config.agent_name, safe="")
    return (
        f"{config.project_endpoint.rstrip('/')}/agents/{name}"
        f"?api-version={FOUNDRY_API_VERSION}"
    )


def _get_agent(config: PublishConfig, rest: RestClient) -> dict[str, Any]:
    response = rest.request("GET", _agent_url(config), scope=FOUNDRY_SCOPE)
    raise_for_status(response, f"GET agent '{config.agent_name}'")
    if not isinstance(response.json, dict):
        raise TalosError(f"GET agent '{config.agent_name}' returned a non-object body")
    return response.json


def _patch_endpoint(
    config: PublishConfig, rest: RestClient, body: dict[str, Any]
) -> None:
    response = rest.request(
        "PATCH",
        _agent_url(config),
        scope=FOUNDRY_SCOPE,
        json_body=body,
        content_type="application/merge-patch+json",
    )
    raise_for_status(
        response, f"enable Activity protocol on agent '{config.agent_name}'"
    )


def _put_bot(
    config: PublishConfig,
    rest: RestClient,
    client_id: str,
    tenant_id: str,
    resolved_bot_arm_id: str,
) -> None:
    url = f"https://management.azure.com{resolved_bot_arm_id}?api-version={BOT_API_VERSION}"
    body = bot_service_body(
        display_name=config.display_name,
        endpoint=activity_protocol_endpoint(config.project_endpoint, config.agent_name),
        client_id=client_id,
        tenant_id=tenant_id,
    )
    response = rest.request("PUT", url, scope=ARM_SCOPE, json_body=body)
    raise_for_status(
        response, f"create or update Azure Bot Service '{config.bot_name}'"
    )


def _put_teams_channel(rest: RestClient, resolved_bot_arm_id: str) -> None:
    url = (
        f"https://management.azure.com{resolved_bot_arm_id}"
        f"/channels/MsTeamsChannel?api-version={BOT_CHANNEL_API_VERSION}"
    )
    response = rest.request("PUT", url, scope=ARM_SCOPE, json_body=teams_channel_body())
    raise_for_status(response, "enable Microsoft Teams channel on Azure Bot Service")


def _post_publish(
    config: PublishConfig,
    rest: RestClient,
    resolved_bot_arm_id: str,
    echo: Echo,
) -> None:
    name = quote(config.agent_name, safe="")
    url = (
        f"{config.project_endpoint.rstrip('/')}/agents/{name}"
        f"/microsoft365/publish?api-version={FOUNDRY_API_VERSION}"
    )
    response = rest.request(
        "POST",
        url,
        scope=FOUNDRY_SCOPE,
        json_body=publish_body(config, resolved_bot_arm_id),
    )
    if response.status_code == 409:
        raise TalosError(
            f"Microsoft 365 app version {config.app_version} already exists; "
            "increment --app-version to update store metadata"
        )
    raise_for_status(response, f"publish agent '{config.agent_name}' to Microsoft 365")
    title_id = _title_id(response)
    if title_id:
        echo(f"published titleId {title_id}")
    else:
        echo("publish succeeded")


def _title_id(response: RestResponse) -> str:
    if isinstance(response.json, dict):
        title = response.json.get("titleId") or response.json.get("title_id")
        if title:
            return str(title)
    return ""


def _echo_dry_run(
    config: PublishConfig,
    subscription_id: str,
    resolved_bot_arm_id: str,
    echo: Echo,
) -> None:
    echo("dry-run: would publish to Microsoft Teams Just you (BotServiceRbac)")
    echo(f"  project: {config.project_endpoint}")
    echo(f"  agent: {config.agent_name}")
    echo(f"  display name: {config.display_name}")
    echo(f"  publishScope: {PUBLISH_SCOPE_JUST_YOU}")
    echo(f"  appVersion: {config.app_version}")
    echo(f"  resource group: {config.resource_group}")
    echo(f"  subscription: {subscription_id}")
    echo(f"  bot: {config.bot_name}")
    echo(f"  bot ARM id: {resolved_bot_arm_id}")
    echo(
        "  activity: "
        f"{activity_protocol_endpoint(config.project_endpoint, config.agent_name)}"
    )
    echo(
        "  endpoint patch: merge-patch protocol_configuration + authorization_schemes "
        "(keep responses/Entra; add activity + BotServiceRbac)"
    )
    echo("  POST /agents/<name>/microsoft365/publish")
