from __future__ import annotations

import pytest
from click.testing import CliRunner

from talos.cli import cli

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


def test_root_help_lists_deploy_and_test() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
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
    ):
        assert flag in result.output


def test_deploy_missing_env_exits_2(clean_azure_env: None) -> None:
    result = CliRunner().invoke(cli, ["deploy", "--no-azd"])
    assert result.exit_code == 2
    assert "Azure environment is not configured" in result.output


def test_deploy_dry_run_prints_plan(clean_azure_env: None) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "deploy",
            "--dry-run",
            "--no-azd",
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
