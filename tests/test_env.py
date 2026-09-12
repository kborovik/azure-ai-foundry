from __future__ import annotations

import pytest

from talos.env import missing_required, parse_azd_values, require_env
from talos.errors import TalosError

pytestmark = pytest.mark.unit


def test_parse_azd_values_strips_quotes_and_skips_comments() -> None:
    raw = """
# comment
AZURE_SEARCH_ENDPOINT="https://srch.example.search.windows.net"

AZURE_AI_PROJECT_ENDPOINT='https://aif.example.services.ai.azure.com/api/projects/demo'
BLANK=

NOT_A_PAIR
"""
    values = parse_azd_values(raw)
    assert values["AZURE_SEARCH_ENDPOINT"] == "https://srch.example.search.windows.net"
    assert (
        values["AZURE_AI_PROJECT_ENDPOINT"]
        == "https://aif.example.services.ai.azure.com/api/projects/demo"
    )
    assert values["BLANK"] == ""
    assert "NOT_A_PAIR" not in values


def test_require_env_exit_code_2() -> None:
    with pytest.raises(TalosError) as exc:
        require_env({})
    assert exc.value.exit_code == 2
    assert "AZURE_SEARCH_ENDPOINT" in str(exc.value)


def test_missing_required_reports_only_blank_names() -> None:
    missing = missing_required({"AZURE_SEARCH_ENDPOINT": "https://srch.example"})
    assert "AZURE_SEARCH_ENDPOINT" not in missing
    assert "AZURE_AI_PROJECT_ENDPOINT" in missing
