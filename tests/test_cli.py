from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

import pytest
from click.testing import CliRunner

from talos import __version__
from talos.cli import cli
from talos.env import repo_root

pytestmark = pytest.mark.unit

SEARCH = "https://srch-cp-demo.search.windows.net"
PROJECT = "https://aif-cp-demo.services.ai.azure.com/api/projects/credit-policy-demo"
PROJECT_ID = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/demo"
    "/providers/Microsoft.CognitiveServices/accounts/aif-cp-demo/projects/credit-policy-demo"
)
STORAGE_ID = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/demo"
    "/providers/Microsoft.Storage/storageAccounts/stcpdemo"
)
AI_SERVICES = "https://aif-cp-demo.services.ai.azure.com"


def test_root_help_lists_generate_deploy_publish_and_chat() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "generate" in result.output
    assert "deploy" in result.output
    assert "publish" in result.output
    assert "chat" in result.output
    assert "--completion" in result.output
    missing = CliRunner().invoke(cli, ["test"])
    assert missing.exit_code != 0
    assert "No such command" in missing.output


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


def test_no_terraform_help_mentions_outputs_json() -> None:
    for cmd in (
        ("generate", "policy"),
        ("generate", "application"),
        ("deploy",),
        ("publish",),
        ("chat",),
    ):
        result = CliRunner().invoke(cli, [*cmd, "--help"])
        assert result.exit_code == 0
        assert "infra/outputs.json" in result.output
        assert "terraform -chdir=infra output -json" not in result.output


def test_bare_generate_prints_help_exit_2() -> None:
    result = CliRunner().invoke(cli, ["generate"])
    assert result.exit_code == 2
    assert "policy" in result.output
    assert "application" in result.output


def test_generate_group_help_lists_policy_and_application() -> None:
    result = CliRunner().invoke(cli, ["generate", "--help"])
    assert result.exit_code == 0
    assert "policy" in result.output
    assert "application" in result.output
    assert (
        "Does not run deploy" in result.output
        or "does not run deploy" in result.output.lower()
    )


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
    assert "ks-client-applications" in result.output
    assert "credit-policy-agent" in result.output


def test_version_option() -> None:
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


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


def test_cli_has_no_pytest_main() -> None:
    text = (repo_root() / "src" / "talos" / "cli.py").read_text(encoding="utf-8")
    assert "pytest.main" not in text
    assert "import pytest" not in text


def test_makefile_test_runs_pytest_and_check_calls_test() -> None:
    makefile = (repo_root() / "Makefile").read_text(encoding="utf-8")
    assert "talos test" not in makefile
    test_match = re.search(r"^test:[^\n]*\n((?:[ \t].*\n)*)", makefile, re.M)
    assert test_match is not None
    assert "$(UV) run pytest" in test_match.group(1)
    check_match = re.search(r"^check:[^\n]*\n((?:[ \t].*\n)*)", makefile, re.M)
    assert check_match is not None
    check = check_match.group(1)
    assert "ruff format --check" in check
    assert "ruff check" in check
    assert "$(MAKE) test" in check


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


def test_gha_unit_workflow_calls_pytest() -> None:
    text = (repo_root() / ".github/workflows/test.yml").read_text(encoding="utf-8")
    assert "uv python install 3.14" in text
    assert "uv run pytest" in text
    assert "talos test" not in text


def test_completion_emits_click_source_for_supported_shells() -> None:
    runner = CliRunner()
    expected = {
        "bash": "_TALOS_COMPLETE",
        "zsh": "_TALOS_COMPLETE",
        "fish": "complete --no-files --command talos",
        "powershell": "_TALOS_COMPLETE",
    }
    for shell, marker in expected.items():
        result = runner.invoke(cli, ["--completion", shell])
        assert result.exit_code == 0, result.output
        assert marker in result.output
        assert "talos" in result.output


def test_completion_unknown_shell_is_usage_error() -> None:
    result = CliRunner().invoke(cli, ["--completion", "nushell"])
    assert result.exit_code != 0
    assert "Invalid value" in result.output or "invalid choice" in result.output.lower()


def test_completion_is_not_a_subcommand() -> None:
    result = CliRunner().invoke(cli, ["completion"])
    assert result.exit_code != 0
    assert "No such command" in result.output
