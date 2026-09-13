from pathlib import Path
from typing import Any

import pytest

from talos.constants import REQUIRED_ENV
from talos.env import apply_dotenv, repo_root as find_repo_root
from tests.helpers import load_facts, load_golden_queries, load_manifest

_DOTENV_CLEAN_NAMES = (
    *REQUIRED_ENV,
    "AZURE_STORAGE_ACCOUNT_URL",
    "AZURE_STORAGE_CONNECTION_STRING",
    "AZURE_RESOURCE_GROUP",
    "AZURE_LOCATION",
    "AZURE_AI_PROJECT_PRINCIPAL_ID",
)


def pytest_configure(config: pytest.Config) -> None:
    apply_dotenv()


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
    for name in _DOTENV_CLEAN_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("talos.env.load_dotenv_file", lambda path=None: {})
