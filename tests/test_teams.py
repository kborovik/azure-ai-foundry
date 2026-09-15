from __future__ import annotations

import os
from typing import Any

import pytest

from talos.env import repo_root
from tests.live_support import (
    assert_expected_decision,
    assert_policy_only_citations,
    invoke_agent,
    pick_application_case,
)


def _activity_enabled(agent: dict[str, Any]) -> bool:
    from talos.provision import activity_protocol_enabled

    return activity_protocol_enabled(agent)


def _require_activity_client(live_env: dict[str, str]) -> None:
    from azure.identity import DefaultAzureCredential

    from talos.constants import DEFAULT_AGENT_NAME, FOUNDRY_SCOPE
    from talos.rest import RequestsRest
    from tests.live_support import get_or_skip

    rest = RequestsRest(DefaultAzureCredential())
    url = (
        f"{live_env['AZURE_AI_PROJECT_ENDPOINT'].rstrip('/')}"
        f"/agents/{DEFAULT_AGENT_NAME}?api-version=v1"
    )
    agent = get_or_skip(rest, url, scope=FOUNDRY_SCOPE, action="GET agent")
    if not _activity_enabled(agent):
        pytest.skip("no Activity client (agent endpoint activity protocol not enabled)")


@pytest.mark.unit
def test_runbook_documents_just_you_and_sideload() -> None:
    path = repo_root() / "docs/teams.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    for needle in (
        "Just you",
        "BotServiceRbac",
        "sideload",
        "Microsoft.BotService",
        "Azure Bot Service Contributor",
        "application_id",
        "customer_name",
        "E2E_TEAMS",
        "talos publish",
        "publishScope",
        "hosted-agents.md",
        "CA-20260914-1789344000000",
        "manifest.json",
    ):
        assert needle in text, needle
    assert "CA-2026-000101" not in text


@pytest.mark.unit
def test_policy_only_citations_allow_paired_application_glyphs() -> None:
    assert_policy_only_citations("ok 【0:1†CP-DOC-2026-01.md】")
    assert_policy_only_citations(
        "ok 【0:1†https://st.blob.core.windows.net/credit-policies/"
        "CP-RML-2026-01-residential-mortgage.md】"
    )
    assert_policy_only_citations(
        "ok 【0:1†CP-DOC-2026-01.md】 【0:2†credit-application-CA-2026-000202.md】"
    )
    assert_policy_only_citations(
        "ok 【0:1†CP-RML-2026-01-residential-mortgage.md】 "
        "【0:2†https://st.blob.core.windows.net/client-applications/"
        "credit-application-CA-2026-000202.md】"
    )
    with pytest.raises(AssertionError):
        assert_policy_only_citations("bad 【0:1†credit-application-CA-2026-000202.md】")
    with pytest.raises(AssertionError):
        assert_policy_only_citations(
            "bad 【0:1†https://st.blob.core.windows.net/client-applications/"
            "credit-application-CA-2026-000202.md】"
        )
    with pytest.raises(AssertionError):
        assert_policy_only_citations("bad 【0:1†accepted.md】")


@pytest.mark.teams
def test_teams_evaluate_by_application_id(live_env: dict[str, str]) -> None:
    _require_activity_client(live_env)
    record = pick_application_case()
    application_id = str(record["application_id"])
    text = invoke_agent(
        live_env,
        f"In Teams 1:1, evaluate application {application_id}.",
    )
    assert application_id in text
    assert_expected_decision(text, str(record["expected_judgement"]))


@pytest.mark.teams
def test_teams_evaluate_by_customer_name(live_env: dict[str, str]) -> None:
    _require_activity_client(live_env)
    record = pick_application_case()
    name = str(record["customer_name"])
    text = invoke_agent(
        live_env,
        f"Evaluate the application for {name}.",
    )
    assert name.split()[0] in text
    assert_expected_decision(text, str(record["expected_judgement"]))


@pytest.mark.teams
def test_teams_flag_is_opt_in() -> None:
    assert os.environ.get("E2E_TEAMS") == "1"
