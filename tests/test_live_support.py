from __future__ import annotations

import pytest

from tests.live_support import print_agent_turn

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
