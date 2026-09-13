from __future__ import annotations

import os
from pathlib import Path

import pytest

from talos.constants import REQUIRED_ENV
from talos.env import (
    apply_dotenv,
    load_dotenv_file,
    missing_required,
    parse_azd_values,
    require_env,
    resolve_env,
    resolve_generate_env,
)
from talos.errors import TalosError

pytestmark = pytest.mark.unit

DOTENV_SEARCH = "https://from-dotenv.search.windows.net"
PROCESS_SEARCH = "https://from-process.search.windows.net"
AZD_SEARCH = "https://from-azd.search.windows.net"


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


def test_load_dotenv_file_missing_returns_empty(tmp_path: Path) -> None:
    assert load_dotenv_file(tmp_path / ".env") == {}


def test_load_dotenv_file_parses_quotes_and_skips_comments(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        '# comment\nAZURE_SEARCH_ENDPOINT="https://srch.example.search.windows.net"\n'
        "AZURE_AI_PROJECT_ENDPOINT='https://aif.example/api/projects/demo'\n\nBLANK=\n",
        encoding="utf-8",
    )
    values = load_dotenv_file(path)
    assert values["AZURE_SEARCH_ENDPOINT"] == "https://srch.example.search.windows.net"
    assert (
        values["AZURE_AI_PROJECT_ENDPOINT"] == "https://aif.example/api/projects/demo"
    )
    assert values["BLANK"] == ""


def test_resolve_env_fills_missing_from_dotenv_not_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZURE_SEARCH_ENDPOINT", raising=False)
    monkeypatch.setenv("AZURE_AI_PROJECT_ENDPOINT", "https://already-set")
    monkeypatch.setattr(
        "talos.env.load_dotenv_file",
        lambda path=None: {
            "AZURE_SEARCH_ENDPOINT": DOTENV_SEARCH,
            "AZURE_AI_PROJECT_ENDPOINT": "https://dotenv-must-not-win",
        },
    )
    monkeypatch.setattr(
        "talos.env.load_azd_env",
        lambda: {"AZURE_SEARCH_ENDPOINT": AZD_SEARCH},
    )
    env = resolve_env(use_azd=True)
    assert env["AZURE_SEARCH_ENDPOINT"] == DOTENV_SEARCH
    assert env["AZURE_AI_PROJECT_ENDPOINT"] == "https://already-set"


def test_resolve_env_process_env_wins_over_dotenv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", PROCESS_SEARCH)
    monkeypatch.setattr(
        "talos.env.load_dotenv_file",
        lambda path=None: {"AZURE_SEARCH_ENDPOINT": DOTENV_SEARCH},
    )
    monkeypatch.setattr("talos.env.load_azd_env", lambda: {})
    env = resolve_env(use_azd=True)
    assert env["AZURE_SEARCH_ENDPOINT"] == PROCESS_SEARCH


def test_resolve_env_dotenv_wins_over_azd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AZURE_SEARCH_ENDPOINT", raising=False)
    monkeypatch.setattr(
        "talos.env.load_dotenv_file",
        lambda path=None: {"AZURE_SEARCH_ENDPOINT": DOTENV_SEARCH},
    )
    monkeypatch.setattr(
        "talos.env.load_azd_env",
        lambda: {"AZURE_SEARCH_ENDPOINT": AZD_SEARCH},
    )
    env = resolve_env(use_azd=True)
    assert env["AZURE_SEARCH_ENDPOINT"] == DOTENV_SEARCH


def test_resolve_env_no_azd_still_loads_dotenv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZURE_SEARCH_ENDPOINT", raising=False)
    monkeypatch.setattr(
        "talos.env.load_dotenv_file",
        lambda path=None: {"AZURE_SEARCH_ENDPOINT": DOTENV_SEARCH},
    )
    called: list[bool] = []
    monkeypatch.setattr(
        "talos.env.load_azd_env",
        lambda: called.append(True) or {"AZURE_SEARCH_ENDPOINT": AZD_SEARCH},
    )
    env = resolve_env(use_azd=False)
    assert env["AZURE_SEARCH_ENDPOINT"] == DOTENV_SEARCH
    assert called == []


def test_resolve_env_azd_fills_after_dotenv_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZURE_SEARCH_ENDPOINT", raising=False)
    monkeypatch.setattr("talos.env.load_dotenv_file", lambda path=None: {})
    monkeypatch.setattr(
        "talos.env.load_azd_env",
        lambda: {"AZURE_SEARCH_ENDPOINT": AZD_SEARCH},
    )
    env = resolve_env(use_azd=True)
    assert env["AZURE_SEARCH_ENDPOINT"] == AZD_SEARCH


def test_resolve_generate_env_fills_storage_url_from_dotenv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT_URL", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.setattr(
        "talos.env.load_dotenv_file",
        lambda path=None: {
            "AZURE_STORAGE_ACCOUNT_URL": "https://stcpdemo.blob.core.windows.net"
        },
    )
    called: list[bool] = []
    monkeypatch.setattr(
        "talos.env.load_azd_env",
        lambda: called.append(True) or {},
    )
    env = resolve_generate_env(use_azd=True)
    assert env["AZURE_STORAGE_ACCOUNT_URL"] == "https://stcpdemo.blob.core.windows.net"
    assert called == []


def test_apply_dotenv_fills_mapping_not_os(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AZURE_SEARCH_ENDPOINT", raising=False)
    path = tmp_path / ".env"
    path.write_text(f"AZURE_SEARCH_ENDPOINT={DOTENV_SEARCH}\n", encoding="utf-8")
    target: dict[str, str] = {}
    apply_dotenv(target, path=path)
    assert target["AZURE_SEARCH_ENDPOINT"] == DOTENV_SEARCH
    assert os.environ.get("AZURE_SEARCH_ENDPOINT") != DOTENV_SEARCH


def test_gitignore_lists_dotenv(repo_root: Path) -> None:
    text = (repo_root / ".gitignore").read_text(encoding="utf-8")
    lines = {line.strip() for line in text.splitlines() if line.strip()}
    assert ".env" in lines
    assert ".env.example" not in lines


def test_env_example_lists_canonical_names(repo_root: Path) -> None:
    from tests.test_infra import BANNED_OUTPUTS, CANONICAL_OUTPUTS

    path = repo_root / ".env.example"
    text = path.read_text(encoding="utf-8")
    parsed = parse_azd_values(text)
    for name in CANONICAL_OUTPUTS:
        assert name in parsed, name
        assert f"{name}=" in text
    for banned in BANNED_OUTPUTS:
        assert banned not in parsed
    assert "AZURE_STORAGE_CONNECTION_STRING" not in parsed
