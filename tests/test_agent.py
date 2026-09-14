from __future__ import annotations

import pytest

from talos.constants import APPLICATION_TYPES, REFUSAL_SENTENCE
from tests.live_support import (
    assert_policy_only_citations,
    citation_glyph_present,
    expected_decision_token,
    invoke_agent,
    pick_application_case,
)

pytestmark = pytest.mark.agent


def test_evaluate_by_application_id(live_env: dict[str, str]) -> None:
    record = pick_application_case("accepted")
    application_id = str(record["application_id"])
    text = invoke_agent(
        live_env,
        f"Evaluate client application {application_id} against published credit policy.",
    )
    lower = text.lower()
    assert application_id in text
    assert expected_decision_token(str(record["expected_judgement"])) in lower
    assert citation_glyph_present(text)
    assert_policy_only_citations(text)


def test_evaluate_by_customer_name(live_env: dict[str, str]) -> None:
    record = pick_application_case("rejected")
    name = str(record["customer_name"])
    text = invoke_agent(
        live_env,
        f"Please evaluate the application for customer {name}.",
    )
    lower = text.lower()
    assert name.split()[0] in text
    assert expected_decision_token(str(record["expected_judgement"])) in lower
    assert citation_glyph_present(text)
    assert_policy_only_citations(text)


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
    record = pick_application_case(application_type)
    text = invoke_agent(
        live_env,
        f"Evaluate application {record['application_id']} for {record['customer_name']}.",
    )
    lower = text.lower()
    assert str(record["application_id"]) in text
    assert expected_decision_token(str(record["expected_judgement"])) in lower
    assert citation_glyph_present(text)
    assert_policy_only_citations(text)


def test_policy_only_out_of_corpus_refuses(live_env: dict[str, str]) -> None:
    text = invoke_agent(live_env, "What is the maximum LTV on a new auto loan?")
    assert (
        REFUSAL_SENTENCE in text.lower()
        or "not in the published policies" in text.lower()
    )
