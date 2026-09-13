from __future__ import annotations

from pathlib import Path

import pytest

from talos.constants import CANONICAL_ENV, REQUIRED_ENV
from talos.env import (
    missing_required,
    parse_terraform_output,
    require_env,
    resolve_env,
    resolve_generate_env,
)
from talos.errors import TalosError

pytestmark = pytest.mark.unit

DOTENV_SEARCH = "https://from-dotenv.search.windows.net"
TF_SEARCH = "https://from-tf.search.windows.net"
DOTENV_STORAGE = "https://from-dotenv.blob.core.windows.net"
TF_STORAGE = "https://from-tf.blob.core.windows.net"

TF_OUTPUT_JSON = """
{
  "AZURE_SEARCH_ENDPOINT": {
    "sensitive": false,
    "type": "string",
    "value": "https://from-tf.search.windows.net"
  },
  "AZURE_AI_PROJECT_ENDPOINT": {
    "sensitive": false,
    "type": "string",
    "value": "https://aif.example.services.ai.azure.com/api/projects/demo"
  },
  "BLANK": {
    "sensitive": false,
    "type": "string",
    "value": ""
  },
  "SEARCH_ENDPOINT": {
    "sensitive": false,
    "type": "string",
    "value": "https://banned.search.windows.net"
  }
}
"""


def _plant_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    (tmp_path / ".env").write_text(text, encoding="utf-8")
    monkeypatch.setattr("talos.env.repo_root", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)


def test_parse_terraform_output_unwraps_value() -> None:
    values = parse_terraform_output(TF_OUTPUT_JSON)
    assert values["AZURE_SEARCH_ENDPOINT"] == TF_SEARCH
    assert (
        values["AZURE_AI_PROJECT_ENDPOINT"]
        == "https://aif.example.services.ai.azure.com/api/projects/demo"
    )
    assert "BLANK" not in values
    assert values["SEARCH_ENDPOINT"] == "https://banned.search.windows.net"


def test_parse_terraform_output_invalid_json_is_empty() -> None:
    assert parse_terraform_output("not-json") == {}
    assert parse_terraform_output("[]") == {}


def test_require_env_exit_code_2() -> None:
    with pytest.raises(TalosError) as exc:
        require_env({})
    assert exc.value.exit_code == 2
    assert "AZURE_SEARCH_ENDPOINT" in str(exc.value)
    assert ".env" not in str(exc.value)
    assert "terraform apply" in str(exc.value)


def test_missing_required_reports_only_blank_names() -> None:
    missing = missing_required({"AZURE_SEARCH_ENDPOINT": "https://srch.example"})
    assert "AZURE_SEARCH_ENDPOINT" not in missing
    assert "AZURE_AI_PROJECT_ENDPOINT" in missing


def test_resolve_env_fills_only_missing_from_terraform(
    clean_azure_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AZURE_AI_PROJECT_ENDPOINT", "https://already-set")
    monkeypatch.setattr(
        "talos.env.load_terraform_output",
        lambda: {
            "AZURE_SEARCH_ENDPOINT": TF_SEARCH,
            "AZURE_AI_PROJECT_ENDPOINT": "https://tf-must-not-win",
        },
    )
    env = resolve_env(use_terraform=True)
    assert env["AZURE_SEARCH_ENDPOINT"] == TF_SEARCH
    assert env["AZURE_AI_PROJECT_ENDPOINT"] == "https://already-set"


def test_resolve_env_no_terraform_does_not_load(
    clean_azure_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[bool] = []
    monkeypatch.setattr(
        "talos.env.load_terraform_output",
        lambda: called.append(True) or {"AZURE_SEARCH_ENDPOINT": TF_SEARCH},
    )
    env = resolve_env(use_terraform=False)
    assert called == []
    assert env.get("AZURE_SEARCH_ENDPOINT") != TF_SEARCH


def test_resolve_env_skips_terraform_when_required_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in REQUIRED_ENV:
        monkeypatch.setenv(name, f"https://{name}.example")
    called: list[bool] = []
    monkeypatch.setattr(
        "talos.env.load_terraform_output", lambda: called.append(True) or {}
    )
    resolve_env(use_terraform=True)
    assert called == []


def test_resolve_env_does_not_load_dotenv_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AZURE_SEARCH_ENDPOINT", raising=False)
    _plant_dotenv(tmp_path, monkeypatch, f"AZURE_SEARCH_ENDPOINT={DOTENV_SEARCH}\n")
    env = resolve_env(use_terraform=False)
    assert env.get("AZURE_SEARCH_ENDPOINT") != DOTENV_SEARCH


def test_resolve_env_no_terraform_ignores_dotenv_and_skips_terraform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AZURE_SEARCH_ENDPOINT", raising=False)
    _plant_dotenv(tmp_path, monkeypatch, f"AZURE_SEARCH_ENDPOINT={DOTENV_SEARCH}\n")
    called: list[bool] = []
    monkeypatch.setattr(
        "talos.env.load_terraform_output",
        lambda: called.append(True) or {"AZURE_SEARCH_ENDPOINT": TF_SEARCH},
    )
    env = resolve_env(use_terraform=False)
    assert env.get("AZURE_SEARCH_ENDPOINT") not in {DOTENV_SEARCH, TF_SEARCH}
    assert called == []


def test_resolve_env_terraform_fills_when_dotenv_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AZURE_SEARCH_ENDPOINT", raising=False)
    _plant_dotenv(tmp_path, monkeypatch, f"AZURE_SEARCH_ENDPOINT={DOTENV_SEARCH}\n")
    monkeypatch.setattr(
        "talos.env.load_terraform_output",
        lambda: {"AZURE_SEARCH_ENDPOINT": TF_SEARCH},
    )
    env = resolve_env(use_terraform=True)
    assert env["AZURE_SEARCH_ENDPOINT"] == TF_SEARCH


def test_resolve_generate_env_skips_terraform_when_process_has_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_URL", TF_STORAGE)
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    called: list[bool] = []
    monkeypatch.setattr(
        "talos.env.load_terraform_output", lambda: called.append(True) or {}
    )
    env = resolve_generate_env(use_terraform=True)
    assert env["AZURE_STORAGE_ACCOUNT_URL"] == TF_STORAGE
    assert called == []


def test_resolve_generate_env_ignores_dotenv_then_calls_terraform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT_URL", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    _plant_dotenv(
        tmp_path, monkeypatch, f"AZURE_STORAGE_ACCOUNT_URL={DOTENV_STORAGE}\n"
    )
    monkeypatch.setattr(
        "talos.env.load_terraform_output",
        lambda: {"AZURE_STORAGE_ACCOUNT_URL": TF_STORAGE},
    )
    env = resolve_generate_env(use_terraform=True)
    assert env["AZURE_STORAGE_ACCOUNT_URL"] == TF_STORAGE


def test_load_terraform_output_keeps_canonical_names_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "talos.env.parse_terraform_output",
        lambda _text: {
            "AZURE_SEARCH_ENDPOINT": TF_SEARCH,
            "SEARCH_ENDPOINT": "https://banned.search.windows.net",
            "FOUNDRY_PROJECT_ENDPOINT": "https://banned.services.ai.azure.com",
        },
    )
    monkeypatch.setattr(
        "talos.env.subprocess.run",
        lambda *args, **kwargs: type(
            "Proc", (), {"returncode": 0, "stdout": "{}", "stderr": ""}
        )(),
    )
    from talos.env import load_terraform_output

    values = load_terraform_output()
    assert values["AZURE_SEARCH_ENDPOINT"] == TF_SEARCH
    assert "SEARCH_ENDPOINT" not in values
    assert "FOUNDRY_PROJECT_ENDPOINT" not in values
    for name in values:
        assert name in CANONICAL_ENV


def test_gitignore_lists_dotenv_and_tfstate(repo_root: Path) -> None:
    text = (repo_root / ".gitignore").read_text(encoding="utf-8")
    lines = {line.strip() for line in text.splitlines() if line.strip()}
    assert ".env" in lines
    assert ".env.example" not in lines
    assert "*.tfstate" in lines
    assert ".terraform/" in lines


def test_env_example_is_not_committed(repo_root: Path) -> None:
    assert not (repo_root / ".env.example").exists()


def test_env_module_has_no_dotenv_or_azd_loaders() -> None:
    import talos.env as env_mod

    assert not hasattr(env_mod, "load_dotenv_file")
    assert not hasattr(env_mod, "apply_dotenv")
    assert not hasattr(env_mod, "load_azd_env")
    assert not hasattr(env_mod, "parse_azd_values")
