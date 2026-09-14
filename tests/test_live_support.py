from __future__ import annotations

import pytest

from tests.live_support import (
    application_cases,
    pick_application_case,
    print_agent_turn,
)

pytestmark = pytest.mark.unit


def test_print_agent_turn_labels_request_and_response(
    capsys: pytest.CaptureFixture[str],
) -> None:
    print_agent_turn(
        "Evaluate client application CA-20260914-1.",
        "I judge this application as accepted.",
    )
    out = capsys.readouterr().out
    request_i = out.index("Agent Request")
    prompt_i = out.index("Evaluate client application CA-20260914-1.")
    response_i = out.index("Agent Response")
    reply_i = out.index("I judge this application as accepted.")
    assert request_i < prompt_i < response_i < reply_i
    assert out.endswith("\n")


def test_application_cases_include_committed_fixtures() -> None:
    cases = application_cases()
    ids = {str(item["application_id"]) for item in cases}
    assert "CA-20260115-1768478400000" in ids
    kinds = {str(item["application_type"]) for item in cases}
    assert kinds >= {"accepted", "rejected", "missing-data"}
    helene = next(
        item for item in cases if item["application_id"] == "CA-20260115-1768478400000"
    )
    assert helene["expected_outcome"] == "accepted"
    assert helene["facility"]["appraisal_date"] == "2026-08-01"


def test_pick_application_case_is_seeded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("E2E_APPLICATION_SEED", "0")
    first = pick_application_case("accepted")
    second = pick_application_case("accepted")
    assert first["application_id"] == second["application_id"]
    assert first["application_type"] == "accepted"
