from pathlib import Path
from typing import Any

import pytest

from talos.constants import REQUIRED_ENV
from talos.env import repo_root as find_repo_root
from tests.helpers import load_facts, load_golden_queries, load_manifest


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
    for name in REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT_URL", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("AZURE_RESOURCE_GROUP", raising=False)
