from __future__ import annotations

import re
from pathlib import Path

import pytest

from talos.constants import (
    CANONICAL_ENV,
    DEFAULT_CHAT_DEPLOYMENT,
    DEFAULT_CONTAINER,
    DEFAULT_EMBEDDING_DEPLOYMENT,
)
from talos.env import repo_root as find_repo_root

pytestmark = pytest.mark.unit

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


def _tf_files() -> list[Path]:
    return sorted(_infra_dir().glob("*.tf"))


def _all_tf() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in _tf_files())


def _read(name: str) -> str:
    return (_infra_dir() / name).read_text(encoding="utf-8")


def test_no_azure_yaml_or_bicep_or_azd(repo_root: Path) -> None:
    assert not (repo_root / "azure.yaml").exists()
    assert list(_infra_dir().rglob("*.bicep")) == []
    assert list(_infra_dir().rglob("*.bicepparam")) == []
    text = _all_tf().lower()
    assert "azure.yaml" not in text
    assert "azd" not in text
    makefile = (repo_root / "Makefile").read_text(encoding="utf-8")
    assert "azd" not in makefile
    assert "need-terraform" in makefile


def test_terraform_does_not_create_knowledge_source_or_agent() -> None:
    text = _all_tf().lower()
    for banned in (
        "knowledgesources",
        "knowledgebases",
        "ks-credit-policies",
        "kb-credit-policies",
        "microsoft.botservice",
        "promptagentdefinition",
        "azurerm_bot_service",
        "azurerm_bot_channels_registration",
    ):
        assert banned not in text, banned


def test_search_sku_is_basic_with_managed_identity() -> None:
    search = _read("search.tf")
    assert "azurerm_search_service" in search
    assert 'sku                           = "basic"' in search or re.search(
        r'sku\s*=\s*"basic"', search
    )
    assert 'sku                           = "free"' not in search
    assert 'sku = "free"' not in search
    assert "SystemAssigned" in search
    assert "replica_count" in search
    assert "partition_count" in search


def test_models_are_gpt5mini_and_text_embedding_3_large() -> None:
    foundry = _read("foundry.tf")
    assert 'kind                          = "AIServices"' in foundry or re.search(
        r'kind\s*=\s*"AIServices"', foundry
    )
    assert 'sku_name                      = "S0"' in foundry or re.search(
        r'sku_name\s*=\s*"S0"', foundry
    )
    assert DEFAULT_CHAT_DEPLOYMENT in foundry
    assert DEFAULT_EMBEDDING_DEPLOYMENT in foundry
    assert 'name    = "gpt-5-mini"' in foundry
    assert 'name    = "text-embedding-3-large"' in foundry
    assert 'name     = "GlobalStandard"' in foundry
    assert "gpt-5.4-mini" not in foundry
    assert "gpt-4.1-mini" not in foundry
    assert "SystemAssigned" in foundry
    assert "project_management_enabled    = true" in foundry or re.search(
        r"project_management_enabled\s*=\s*true", foundry
    )
    assert "credit-policy-demo" in _read("variables.tf")
    assert "azurerm_cognitive_account_project" in foundry


def test_location_defaults_to_swedencentral_and_blocks_footnote_regions() -> None:
    variables = _read("variables.tf")
    assert 'default     = "swedencentral"' in variables or re.search(
        r'default\s*=\s*"swedencentral"', variables
    )
    allowed = re.search(r"contains\(\[(.*?)\], var\.location\)", variables, re.S)
    assert allowed is not None
    allowed_block = allowed.group(1)
    for region in ALLOWED_LOCATIONS:
        assert f'"{region}"' in allowed_block, region
    for region in BLOCKED_LOCATIONS:
        assert f'"{region}"' not in allowed_block, region


def test_canonical_outputs_only() -> None:
    outputs = _read("outputs.tf")
    names = re.findall(r'^output "(\S+)"', outputs, re.M)
    assert tuple(names) == CANONICAL_ENV
    for banned in BANNED_OUTPUTS:
        assert banned not in names
    assert "AZURE_AI_PROJECT_PRINCIPAL_ID" in outputs
    assert "AZURE_AI_SERVICES_ENDPOINT" in outputs
    assert "services.ai.azure.com" in outputs


def test_resource_names_match_spec() -> None:
    main = _read("main.tf")
    assert "rg-credit-policy-${var.environment_name}" in main
    assert "stcp${local.resource_token}" in main
    assert "srch-cp-${local.resource_token}" in main
    assert "aif-cp-${local.resource_token}" in main
    assert "credit-policy-demo" in _read("variables.tf")
    storage = _read("storage.tf")
    assert DEFAULT_CONTAINER in storage
    assert "allow_nested_items_to_be_public = false" in storage
    assert 'min_tls_version                 = "TLS1_2"' in storage or re.search(
        r'min_tls_version\s*=\s*"TLS1_2"', storage
    )


def test_rbac_project_mi_reads_search_and_search_mi_reads_storage_and_foundry() -> None:
    rbac = _read("rbac.tf")
    assert STORAGE_BLOB_DATA_READER in rbac
    assert COGNITIVE_SERVICES_USER in rbac
    assert SEARCH_INDEX_DATA_READER in rbac
    assert "search_reads_blobs" in rbac
    assert "search_uses_foundry" in rbac
    assert "project_reads_search" in rbac
    assert 'principal_type                   = "ServicePrincipal"' in rbac or re.search(
        r'principal_type\s*=\s*"ServicePrincipal"', rbac
    )


def test_local_auth_keys_not_disabled() -> None:
    text = _all_tf()
    assert "disableLocalAuth" not in text
    assert "local_auth_enabled            = false" not in text
    assert "local_authentication_enabled  = false" not in text
    assert re.search(r"local_auth_enabled\s*=\s*false", text) is None
    assert re.search(r"local_authentication_enabled\s*=\s*false", text) is None


def test_chat_capacity_is_50_not_50000() -> None:
    variables = _read("variables.tf")
    foundry = _read("foundry.tf")
    assert "default     = 50" in variables or re.search(
        r"variable \"chat_capacity\".*?default\s*=\s*50", variables, re.S
    )
    assert "capacity = var.chat_capacity" in foundry
    assert re.search(r"chat_capacity[\s\S]*default\s*=\s*50000", variables) is None
    assert re.search(r"capacity\s*=\s*50000", foundry) is None
    assert "default     = 20" in variables or re.search(
        r"variable \"embedding_capacity\".*?default\s*=\s*20", variables, re.S
    )


def test_no_application_insights() -> None:
    text = _all_tf()
    for banned in (
        "azurerm_application_insights",
        "Microsoft.Insights/components",
        "applicationInsights",
        "Application Insights",
        "appInsights",
        "application_insights",
    ):
        assert banned.lower() not in text.lower(), banned
