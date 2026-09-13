from __future__ import annotations

from pathlib import Path

import pytest

from talos.constants import REQUIRED_ENV
from talos.env import (
    missing_required,
    parse_azd_values,
    require_env,
    resolve_env,
    resolve_generate_env,
)
from talos.errors import TalosError

pytestmark = pytest.mark.unit

DOTENV_SEARCH = "https://from-dotenv.search.windows.net"
AZD_SEARCH = "https://from-azd.search.windows.net"
DOTENV_STORAGE = "https://from-dotenv.blob.core.windows.net"
AZD_STORAGE = "https://from-azd.blob.core.windows.net"


def _plant_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    (tmp_path / ".env").write_text(text, encoding="utf-8")
    monkeypatch.setattr("talos.env.repo_root", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)


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
    assert ".env" not in str(exc.value)


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
            "AZURE_SEARCH_ENDPOINT": AZD_SEARCH,
            "AZURE_AI_PROJECT_ENDPOINT": "https://azd-must-not-win",
        },
    )
    env = resolve_env(use_azd=True)
    assert env["AZURE_SEARCH_ENDPOINT"] == AZD_SEARCH
    assert env["AZURE_AI_PROJECT_ENDPOINT"] == "https://already-set"


def test_resolve_env_no_azd_does_not_load(
    clean_azure_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[bool] = []
    monkeypatch.setattr(
        "talos.env.load_azd_env",
        lambda: (
            called.append(True)
            or {"AZURE_SEARCH_ENDPOINT": AZD_SEARCH}
        ),
    )
    env = resolve_env(use_azd=False)
    assert called == []
    assert env.get("AZURE_SEARCH_ENDPOINT") != AZD_SEARCH


def test_resolve_env_skips_azd_when_required_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in REQUIRED_ENV:
        monkeypatch.setenv(name, f"https://{name}.example")
    called: list[bool] = []
    monkeypatch.setattr("talos.env.load_azd_env", lambda: called.append(True) or {})
    resolve_env(use_azd=True)
    assert called == []


def test_resolve_env_does_not_load_dotenv_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AZURE_SEARCH_ENDPOINT", raising=False)
    _plant_dotenv(tmp_path, monkeypatch, f"AZURE_SEARCH_ENDPOINT={DOTENV_SEARCH}\n")
    env = resolve_env(use_azd=False)
    assert env.get("AZURE_SEARCH_ENDPOINT") != DOTENV_SEARCH


def test_resolve_env_no_azd_ignores_dotenv_and_skips_azd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AZURE_SEARCH_ENDPOINT", raising=False)
    _plant_dotenv(tmp_path, monkeypatch, f"AZURE_SEARCH_ENDPOINT={DOTENV_SEARCH}\n")
    called: list[bool] = []
    monkeypatch.setattr(
        "talos.env.load_azd_env",
        lambda: called.append(True) or {"AZURE_SEARCH_ENDPOINT": AZD_SEARCH},
    )
    env = resolve_env(use_azd=False)
    assert env.get("AZURE_SEARCH_ENDPOINT") not in {DOTENV_SEARCH, AZD_SEARCH}
    assert called == []


def test_resolve_env_azd_fills_when_dotenv_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AZURE_SEARCH_ENDPOINT", raising=False)
    _plant_dotenv(tmp_path, monkeypatch, f"AZURE_SEARCH_ENDPOINT={DOTENV_SEARCH}\n")
    monkeypatch.setattr(
        "talos.env.load_azd_env",
        lambda: {"AZURE_SEARCH_ENDPOINT": AZD_SEARCH},
    )
    env = resolve_env(use_azd=True)
    assert env["AZURE_SEARCH_ENDPOINT"] == AZD_SEARCH


def test_resolve_generate_env_skips_azd_when_process_has_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_URL", AZD_STORAGE)
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    called: list[bool] = []
    monkeypatch.setattr("talos.env.load_azd_env", lambda: called.append(True) or {})
    env = resolve_generate_env(use_azd=True)
    assert env["AZURE_STORAGE_ACCOUNT_URL"] == AZD_STORAGE
    assert called == []


def test_resolve_generate_env_ignores_dotenv_then_calls_azd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT_URL", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    _plant_dotenv(
        tmp_path, monkeypatch, f"AZURE_STORAGE_ACCOUNT_URL={DOTENV_STORAGE}\n"
    )
    monkeypatch.setattr(
        "talos.env.load_azd_env",
        lambda: {"AZURE_STORAGE_ACCOUNT_URL": AZD_STORAGE},
    )
    env = resolve_generate_env(use_azd=True)
    assert env["AZURE_STORAGE_ACCOUNT_URL"] == AZD_STORAGE


def test_gitignore_lists_dotenv(repo_root: Path) -> None:
    text = (repo_root / ".gitignore").read_text(encoding="utf-8")
    lines = {line.strip() for line in text.splitlines() if line.strip()}
    assert ".env" in lines
    assert ".env.example" not in lines


def test_env_example_is_not_committed(repo_root: Path) -> None:
    assert not (repo_root / ".env.example").exists()


def test_env_module_has_no_dotenv_loaders() -> None:
    import talos.env as env_mod

    assert not hasattr(env_mod, "load_dotenv_file")
    assert not hasattr(env_mod, "apply_dotenv")
