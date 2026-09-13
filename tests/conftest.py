import os
from pathlib import Path
from typing import Any

import pytest

from talos.constants import REQUIRED_ENV
from talos.env import fill_missing, load_terraform_output, repo_root as find_repo_root
from tests.helpers import load_facts, load_golden_queries, load_manifest

_AZURE_ENV_NAMES = (
    *REQUIRED_ENV,
    "AZURE_STORAGE_ACCOUNT_URL",
    "AZURE_STORAGE_CONNECTION_STRING",
    "AZURE_RESOURCE_GROUP",
    "AZURE_LOCATION",
    "AZURE_AI_PROJECT_PRINCIPAL_ID",
)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--no-terraform",
        action="store_true",
        default=False,
        help="Do not fill missing env vars from `terraform -chdir=infra output -json`.",
    )


@pytest.fixture(scope="session", autouse=True)
def fill_terraform_env(request: pytest.FixtureRequest) -> None:
    if request.config.getoption("--no-terraform"):
        return
    fill_missing(os.environ, load_terraform_output())


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return find_repo_root()


@pytest.fixture(scope="session")
def facts(repo_root: Path) -> dict[str, Any]:
    return load_facts(repo_root)


@pytest.fixture(scope="session")
def manifest(repo_root: Path) -> dict[str, Any]:
    return load_manifest(repo_root)


@pytest.fixture(scope="session")
def golden_queries(repo_root: Path) -> list[dict[str, Any]]:
    return load_golden_queries(repo_root)


@pytest.fixture
def clean_azure_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _AZURE_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
