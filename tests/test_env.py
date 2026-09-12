from __future__ import annotations

import pytest

from talos.constants import REQUIRED_ENV
from talos.env import missing_required, parse_azd_values, require_env, resolve_env
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


def test_resolve_env_fills_only_missing_from_azd(
    clean_azure_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AZURE_AI_PROJECT_ENDPOINT", "https://already-set")
    monkeypatch.setattr(
        "talos.env.load_azd_env",
        lambda: {
            "AZURE_SEARCH_ENDPOINT": "https://from-azd.search.windows.net",
            "AZURE_AI_PROJECT_ENDPOINT": "https://azd-must-not-win",
        },
    )
    env = resolve_env(use_azd=True)
    assert env["AZURE_SEARCH_ENDPOINT"] == "https://from-azd.search.windows.net"
    assert env["AZURE_AI_PROJECT_ENDPOINT"] == "https://already-set"


def test_resolve_env_no_azd_does_not_load(
    clean_azure_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[bool] = []
    monkeypatch.setattr(
        "talos.env.load_azd_env",
        lambda: (
            called.append(True)
            or {"AZURE_SEARCH_ENDPOINT": "https://from-azd.search.windows.net"}
        ),
    )
    env = resolve_env(use_azd=False)
    assert called == []
    assert env.get("AZURE_SEARCH_ENDPOINT") != "https://from-azd.search.windows.net"


def test_resolve_env_skips_azd_when_required_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in REQUIRED_ENV:
        monkeypatch.setenv(name, f"https://{name}.example")
    called: list[bool] = []
    monkeypatch.setattr("talos.env.load_azd_env", lambda: called.append(True) or {})
    resolve_env(use_azd=True)
    assert called == []
