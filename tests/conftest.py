import pytest

from talos.constants import REQUIRED_ENV


@pytest.fixture
def clean_azure_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT_URL", raising=False)
    monkeypatch.delenv("AZURE_RESOURCE_GROUP", raising=False)
