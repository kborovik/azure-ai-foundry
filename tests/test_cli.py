from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest
from click.testing import CliRunner

from talos.cli import cli
from talos.env import repo_root

pytestmark = pytest.mark.unit

SEARCH = "https://srch-cp-demo.search.windows.net"
PROJECT = "https://aif-cp-demo.services.ai.azure.com/api/projects/credit-policy-demo"
PROJECT_ID = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-demo"
    "/providers/Microsoft.CognitiveServices/accounts/aif-cp-demo/projects/credit-policy-demo"
)
STORAGE_ID = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-demo"
    "/providers/Microsoft.Storage/storageAccounts/stcpdemo"
)
AI_SERVICES = "https://aif-cp-demo.services.ai.azure.com"


def test_root_help_lists_generate_deploy_and_test() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "generate" in result.output
    assert "deploy" in result.output
    assert "test" in result.output


def test_deploy_help_documents_plan_flags() -> None:
    result = CliRunner().invoke(cli, ["deploy", "--help"])
    assert result.exit_code == 0
    for flag in (
        "--search-endpoint",
        "--project-endpoint",
        "--wait",
        "--skip-indexer-run",
        "--skip-endpoint-patch",
        "--dry-run",
        "--no-terraform",
    ):
        assert flag in result.output


def test_deploy_missing_env_exits_2(clean_azure_env: None) -> None:
    result = CliRunner().invoke(cli, ["deploy", "--no-terraform"])
    assert result.exit_code == 2
    assert "Azure environment is not configured" in result.output


def test_deploy_dry_run_prints_plan(clean_azure_env: None) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "deploy",
            "--dry-run",
            "--no-terraform",
            "--search-endpoint",
            SEARCH,
            "--project-endpoint",
            PROJECT,
            "--project-resource-id",
            PROJECT_ID,
            "--storage-resource-id",
            STORAGE_ID,
            "--ai-services-endpoint",
            AI_SERVICES,
        ],
    )
    assert result.exit_code == 0, result.output
    assert "dry-run" in result.output
    connection_lines = [
        line for line in result.output.splitlines() if "ResourceId=" in line
    ]
    assert connection_lines
    assert connection_lines[0].rstrip().endswith(STORAGE_ID)
    assert not connection_lines[0].rstrip().endswith(";")
    assert "ks-credit-policies" in result.output
    assert "credit-policy-agent" in result.output


def test_version_option() -> None:
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_deploy_flags_override_env(
    clean_azure_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://from-env.search.windows.net")
    monkeypatch.setenv("AZURE_AI_PROJECT_ENDPOINT", PROJECT)
    monkeypatch.setenv("AZURE_AI_PROJECT_RESOURCE_ID", PROJECT_ID)
    monkeypatch.setenv("AZURE_STORAGE_RESOURCE_ID", STORAGE_ID)
    monkeypatch.setenv("AZURE_AI_SERVICES_ENDPOINT", AI_SERVICES)
    result = CliRunner().invoke(
        cli,
        ["deploy", "--dry-run", "--no-terraform", "--search-endpoint", SEARCH],
    )
    assert result.exit_code == 0, result.output
    assert f"search: {SEARCH}" in result.output
    assert "from-env" not in result.output


def test_deploy_reads_canonical_env_without_flags(
    clean_azure_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", SEARCH)
    monkeypatch.setenv("AZURE_AI_PROJECT_ENDPOINT", PROJECT)
    monkeypatch.setenv("AZURE_AI_PROJECT_RESOURCE_ID", PROJECT_ID)
    monkeypatch.setenv("AZURE_STORAGE_RESOURCE_ID", STORAGE_ID)
    monkeypatch.setenv("AZURE_AI_SERVICES_ENDPOINT", AI_SERVICES)
    result = CliRunner().invoke(cli, ["deploy", "--dry-run", "--no-terraform"])
    assert result.exit_code == 0, result.output
    assert f"search: {SEARCH}" in result.output


def test_deploy_no_terraform_does_not_read_dotenv(
    clean_azure_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "\n".join(
            [
                f"AZURE_SEARCH_ENDPOINT={SEARCH}",
                f"AZURE_AI_PROJECT_ENDPOINT={PROJECT}",
                f"AZURE_AI_PROJECT_RESOURCE_ID={PROJECT_ID}",
                f"AZURE_STORAGE_RESOURCE_ID={STORAGE_ID}",
                f"AZURE_AI_SERVICES_ENDPOINT={AI_SERVICES}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("talos.env.repo_root", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["deploy", "--dry-run", "--no-terraform"])
    assert result.exit_code == 2
    assert "Azure environment is not configured" in result.output


def test_test_command_forwards_args(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def fake_main(args: list[str]) -> int:
        seen.append(list(args))
        return 0

    monkeypatch.setattr("pytest.main", fake_main)
    result = CliRunner().invoke(cli, ["test", "-q", "-m", "unit"])
    assert result.exit_code == 0, result.output
    assert seen == [["-q", "-m", "unit"]]


def test_pyproject_talos_cli_contract() -> None:
    data = tomllib.loads((repo_root() / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["requires-python"] == ">=3.14"
    assert data["project"]["scripts"]["talos"] == "talos.cli:cli"
    assert data["tool"]["uv"]["python-preference"] == "managed"
    assert data["tool"]["pytest"]["ini_options"]["addopts"] == "-m unit"
    assert sys.version_info >= (3, 14)


def test_src_has_no_pep_723_scripts() -> None:
    src = repo_root() / "src"
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "# /// script" not in text, path


def test_gha_unit_workflow_calls_talos() -> None:
    text = (repo_root() / ".github/workflows/test.yml").read_text(encoding="utf-8")
    assert "uv python install 3.14" in text
    assert "uv run talos test" in text
