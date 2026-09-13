from __future__ import annotations

from typing import Any

import pytest

from talos.application import parse_application_markdown
from talos.constants import (
    APPLICATION_TYPES,
    DEFAULT_AGENT_NAME,
    DEFAULT_KNOWLEDGE_BASE,
    FOUNDRY_SCOPE,
    SEARCH_API_VERSION,
    SEARCH_SCOPE,
)
from talos.env import repo_root
from talos.rest import RestClient, RestResponse, raise_for_status
from tests.helpers import APPLICATION_FIXTURES_RELATIVE, APPLICATION_OUTPUT_RELATIVE


def search_url(env: dict[str, str], path: str) -> str:
    return (
        f"{env['AZURE_SEARCH_ENDPOINT'].rstrip('/')}/{path}"
        f"?api-version={SEARCH_API_VERSION}"
    )


def get_or_skip(
    rest: RestClient, url: str, *, scope: str, action: str
) -> dict[str, Any]:
    response = rest.request("GET", url, scope=scope)
    if response.status_code in {401, 403, 404}:
        pytest.skip(f"{action} unavailable ({response.status_code})")
    raise_for_status(response, action)
    if not isinstance(response.json, dict):
        pytest.skip(f"{action} returned a non-object body")
    return response.json


def post_or_skip(
    rest: RestClient,
    url: str,
    *,
    scope: str,
    json_body: Any,
    action: str,
    timeout: float = 120.0,
) -> RestResponse:
    response = rest.request(
        "POST", url, scope=scope, json_body=json_body, timeout=timeout
    )
    if response.status_code in {401, 403, 404}:
        pytest.skip(f"{action} unavailable ({response.status_code})")
    raise_for_status(response, action)
    return response


def retrieve(rest: RestClient, env: dict[str, str], query: str) -> dict[str, Any]:
    url = search_url(env, f"knowledgebases/{DEFAULT_KNOWLEDGE_BASE}/retrieve")
    response = post_or_skip(
        rest,
        url,
        scope=SEARCH_SCOPE,
        json_body={
            "includeActivity": True,
            "retrievalReasoningEffort": {"kind": "low"},
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": query}],
                }
            ],
        },
        action="knowledge base retrieve",
        timeout=120.0,
    )
    body = response.json
    return body if isinstance(body, dict) else {}


def invoke_agent(env: dict[str, str], user_text: str) -> str:
    from azure.identity import DefaultAzureCredential

    from talos.rest import RequestsRest

    rest = RequestsRest(DefaultAzureCredential())
    url = f"{env['AZURE_AI_PROJECT_ENDPOINT'].rstrip('/')}/openai/v1/responses"
    response = post_or_skip(
        rest,
        url,
        scope=FOUNDRY_SCOPE,
        json_body={
            "input": user_text,
            "agent_reference": {
                "name": DEFAULT_AGENT_NAME,
                "type": "agent_reference",
            },
        },
        action="agent responses",
        timeout=180.0,
    )
    payload = response.json if isinstance(response.json, dict) else {}
    text = _response_output_text(payload)
    if not text.strip():
        pytest.skip("agent responses returned empty text")
    return text


def _response_output_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    chunks: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks)


def application_cases() -> list[dict[str, Any]]:
    live = repo_root() / APPLICATION_OUTPUT_RELATIVE
    base = (
        live if any(live.glob("*.md")) else repo_root() / APPLICATION_FIXTURES_RELATIVE
    )
    cases: list[dict[str, Any]] = []
    for kind in APPLICATION_TYPES:
        path = base / f"{kind}.md"
        if not path.is_file():
            continue
        record = parse_application_markdown(path.read_text(encoding="utf-8"))
        cases.append(record)
    return cases


def knowledge_source_status(
    rest: RestClient, env: dict[str, str], name: str
) -> dict[str, Any]:
    url = search_url(env, f"knowledgesources/{name}/status")
    return get_or_skip(
        rest, url, scope=SEARCH_SCOPE, action=f"GET knowledge source {name} status"
    )


def flatten_retrieve_text(body: dict[str, Any]) -> str:
    return str(body)


def citation_glyph_present(text: str) -> bool:
    return "【" in text and "†" in text and "】" in text
