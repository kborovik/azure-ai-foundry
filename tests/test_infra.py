from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from talos.constants import (
    DEFAULT_CHAT_DEPLOYMENT,
    DEFAULT_CONTAINER,
    DEFAULT_EMBEDDING_DEPLOYMENT,
)
from talos.env import repo_root as find_repo_root

pytestmark = pytest.mark.unit

CANONICAL_OUTPUTS = (
    "AZURE_LOCATION",
    "AZURE_RESOURCE_GROUP",
    "AZURE_STORAGE_ACCOUNT_URL",
    "AZURE_STORAGE_RESOURCE_ID",
    "AZURE_SEARCH_ENDPOINT",
    "AZURE_AI_PROJECT_ENDPOINT",
    "AZURE_AI_PROJECT_RESOURCE_ID",
    "AZURE_AI_SERVICES_ENDPOINT",
    "AZURE_AI_PROJECT_PRINCIPAL_ID",
)
BANNED_OUTPUTS = ("SEARCH_ENDPOINT", "FOUNDRY_PROJECT_ENDPOINT")
ALLOWED_LOCATIONS = (
    "swedencentral",
    "uksouth",
    "francecentral",
    "canadaeast",
    "centralus",
)
BLOCKED_LOCATIONS = ("eastus", "eastus2", "westus", "westus3", "westus2")
STORAGE_BLOB_DATA_READER = "2a2b9908-6ea1-4ae2-8e65-a410df84e7d1"
COGNITIVE_SERVICES_USER = "a97b65f3-24c7-4388-baec-2e87135dc908"
SEARCH_INDEX_DATA_READER = "1407120a-92aa-4202-b7e9-c0e197c71c8f"


def _infra_dir() -> Path:
    return find_repo_root() / "infra"


def _bicep_files() -> list[Path]:
    return sorted(_infra_dir().rglob("*.bicep"))


def _all_bicep() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in _bicep_files())


def _main_bicep() -> str:
    return (_infra_dir() / "main.bicep").read_text(encoding="utf-8")


def _azure_yaml() -> dict:
    data = yaml.safe_load((find_repo_root() / "azure.yaml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_azure_yaml_module_is_main_not_bicep_filename() -> None:
    data = _azure_yaml()
    assert data["infra"]["path"] == "infra"
    assert data["infra"]["module"] == "main"
    assert data["infra"]["module"] != "main.bicep"
    assert "services" not in data


def test_bicep_does_not_create_knowledge_source_or_agent(repo_root: Path) -> None:
    text = _all_bicep().lower()
    for banned in (
        "knowledgesources",
        "knowledgebases",
        "ks-credit-policies",
        "kb-credit-policies",
        "microsoft.botservice",
        "promptagentdefinition",
    ):
        assert banned not in text, banned
    azure = (repo_root / "azure.yaml").read_text(encoding="utf-8")
    assert "host:" not in azure
    assert "language: python" not in azure


def test_search_sku_is_basic_with_managed_identity() -> None:
    search = (_infra_dir() / "modules" / "search.bicep").read_text(encoding="utf-8")
    assert "Microsoft.Search/searchServices@" in search
    assert re.search(r"sku:\s*\{\s*name:\s*'basic'", search)
    assert "name: 'free'" not in search
    assert "type: 'SystemAssigned'" in search
    assert "replicaCount: 1" in search
    assert "partitionCount: 1" in search


def test_models_are_gpt5mini_and_text_embedding_3_large() -> None:
    foundry = (_infra_dir() / "modules" / "foundry.bicep").read_text(encoding="utf-8")
    assert "kind: 'AIServices'" in foundry
    assert "name: 'S0'" in foundry
    assert DEFAULT_CHAT_DEPLOYMENT in foundry
    assert DEFAULT_EMBEDDING_DEPLOYMENT in foundry
    assert "name: 'gpt-5-mini'" in foundry
    assert "name: 'text-embedding-3-large'" in foundry
    assert "name: 'GlobalStandard'" in foundry
    assert "gpt-5.4-mini" not in foundry
    assert "gpt-4.1-mini" not in foundry
    assert "type: 'SystemAssigned'" in foundry
    assert "allowProjectManagement: true" in foundry
    assert "name: projectName" in foundry
    assert "credit-policy-demo" in foundry


def test_location_defaults_to_swedencentral_and_blocks_footnote_regions() -> None:
    main = _main_bicep()
    assert "param location string = 'swedencentral'" in main
    allowed = re.search(r"@allowed\(\[(.*?)\]\)", main, re.S)
    assert allowed is not None
    allowed_block = allowed.group(1)
    for region in ALLOWED_LOCATIONS:
        assert f"'{region}'" in allowed_block, region
    for region in BLOCKED_LOCATIONS:
        assert f"'{region}'" not in allowed_block, region
    params = json.loads(
        (_infra_dir() / "main.parameters.json").read_text(encoding="utf-8")
    )
    assert params["parameters"]["location"]["value"] == "${AZURE_LOCATION}"


def test_canonical_outputs_only() -> None:
    main = _main_bicep()
    outputs = re.findall(r"^output (\S+) ", main, re.M)
    assert tuple(outputs) == CANONICAL_OUTPUTS
    output_names = set(outputs)
    for banned in BANNED_OUTPUTS:
        assert banned not in output_names
    assert "AZURE_AI_PROJECT_PRINCIPAL_ID" in main
    assert "AZURE_AI_SERVICES_ENDPOINT" in main
    assert "services.ai.azure.com" in (
        _infra_dir() / "modules" / "foundry.bicep"
    ).read_text(encoding="utf-8")


def test_resource_names_match_spec() -> None:
    main = _main_bicep()
    assert "rg-credit-policy-${environmentName}" in main
    assert "stcp${resourceToken}" in main
    assert "srch-cp-${resourceToken}" in main
    assert "aif-cp-${resourceToken}" in main
    assert "credit-policy-demo" in main
    storage = (_infra_dir() / "modules" / "storage.bicep").read_text(encoding="utf-8")
    assert DEFAULT_CONTAINER in storage
    assert "allowBlobPublicAccess: false" in storage
    assert "minimumTlsVersion: 'TLS1_2'" in storage


def test_rbac_project_mi_reads_search_and_search_mi_reads_storage_and_foundry() -> None:
    rbac = (_infra_dir() / "modules" / "rbac.bicep").read_text(encoding="utf-8")
    assert STORAGE_BLOB_DATA_READER in rbac
    assert COGNITIVE_SERVICES_USER in rbac
    assert SEARCH_INDEX_DATA_READER in rbac
    assert "searchPrincipalId" in rbac
    assert "projectPrincipalId" in rbac
    assert "principalType: 'ServicePrincipal'" in rbac
    search_blob = (
        "guid(storage.id, searchPrincipalId, storageBlobDataReader)" in rbac
        or STORAGE_BLOB_DATA_READER in rbac
    )
    assert search_blob
    assert "guid(foundry.id, searchPrincipalId, cognitiveServicesUser)" in rbac
    assert "guid(search.id, projectPrincipalId, searchIndexDataReader)" in rbac


def test_local_auth_keys_not_disabled() -> None:
    text = _all_bicep()
    assert "disableLocalAuth: true" not in text
    assert "disableLocalAuth:true" not in text.replace(" ", "")


def test_chat_capacity_is_50_not_50000() -> None:
    main = _main_bicep()
    foundry = (_infra_dir() / "modules" / "foundry.bicep").read_text(encoding="utf-8")
    assert "param chatCapacity int = 50" in main
    assert "param chatCapacity int = 50" in foundry
    assert "capacity: chatCapacity" in foundry
    assert not re.search(r"chatCapacity int = 50000", main)
    assert not re.search(r"capacity:\s*50000", foundry)
    assert "param embeddingCapacity int = 20" in foundry


def test_no_application_insights() -> None:
    text = _all_bicep()
    for banned in (
        "Microsoft.Insights/components",
        "applicationInsights",
        "Application Insights",
        "appInsights",
    ):
        assert banned.lower() not in text.lower(), banned
