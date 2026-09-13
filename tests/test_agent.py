from __future__ import annotations

import pytest

from talos.constants import APPLICATION_TYPES, REFUSAL_SENTENCE
from tests.live_support import application_cases, citation_glyph_present, invoke_agent

pytestmark = pytest.mark.agent


def test_evaluate_by_application_id(live_env: dict[str, str]) -> None:
    cases = [
        item
        for item in application_cases()
        if item.get("application_type") == "accepted"
    ]
    if not cases:
        pytest.skip("no accepted application fixture")
    application_id = str(cases[0]["application_id"])
    text = invoke_agent(
        live_env,
        f"Evaluate client application {application_id} against published credit policy.",
    )
    lower = text.lower()
    assert application_id in text or "accept" in lower
    assert citation_glyph_present(text)
    assert ".md" not in text.split("†")[-1] or "CP-" in text


def test_evaluate_by_customer_name(live_env: dict[str, str]) -> None:
    cases = [
        item
        for item in application_cases()
        if item.get("application_type") == "rejected"
    ]
    if not cases:
        pytest.skip("no rejected application fixture")
    name = str(cases[0]["customer_name"])
    text = invoke_agent(
        live_env,
        f"Please evaluate the application for customer {name}.",
    )
    lower = text.lower()
    assert name.split()[0] in text or "reject" in lower
    assert citation_glyph_present(text)
    assert "accepted.md" not in text and "rejected.md" not in text


def test_ask_when_missing_identifier(live_env: dict[str, str]) -> None:
    text = invoke_agent(
        live_env,
        "Please evaluate the client application against policy.",
    )
    lower = text.lower()
    assert (
        "application_id" in lower
        or "customer_name" in lower
        or "which application" in lower
    )
    assert "i judge" not in lower


@pytest.mark.parametrize("application_type", APPLICATION_TYPES)
def test_one_case_per_application_type(
    live_env: dict[str, str], application_type: str
) -> None:
    cases = [
        item
        for item in application_cases()
        if item.get("application_type") == application_type
    ]
    if not cases:
        pytest.skip(f"no {application_type} application")
    record = cases[0]
    text = invoke_agent(
        live_env,
        f"Evaluate application {record['application_id']} for {record['customer_name']}.",
    )
    lower = text.lower()
    expected = str(record["expected_judgement"])
    token = (
        "accept"
        if expected == "accepted"
        else ("reject" if expected == "rejected" else "missing")
    )
    assert token in lower
    assert citation_glyph_present(text)


def test_policy_only_out_of_corpus_refuses(live_env: dict[str, str]) -> None:
    text = invoke_agent(live_env, "What is the maximum LTV on a new auto loan?")
    assert (
        REFUSAL_SENTENCE in text.lower()
        or "not in the published policies" in text.lower()
    )
