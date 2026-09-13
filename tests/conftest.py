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
        help="Do not fill missing env vars from `infra/outputs.json`.",
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


def pytest_runtest_setup(item: pytest.Item) -> None:
    if item.get_closest_marker("teams") and os.environ.get("E2E_TEAMS") != "1":
        pytest.skip("teams skip unless E2E_TEAMS=1")


@pytest.fixture(scope="session")
def live_env() -> dict[str, str]:
    from talos.env import missing_required, resolve_env

    env = resolve_env(use_terraform=True)
    missing = missing_required(env)
    if missing:
        pytest.skip("live Azure env missing: " + ", ".join(missing))
    return env


@pytest.fixture(scope="session")
def live_rest(live_env: dict[str, str]) -> Any:
    from azure.identity import DefaultAzureCredential

    from talos.rest import RequestsRest

    return RequestsRest(DefaultAzureCredential())
