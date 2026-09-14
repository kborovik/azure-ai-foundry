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


def _makefile_recipe(makefile: str, target: str) -> str:
    match = re.search(
        rf"^{re.escape(target)}:[^\n]*\n((?:[ \t].*\n)*)",
        makefile,
        re.M,
    )
    assert match is not None, target
    return match.group(1)


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
    assert "credit-policy-demo" in _read("main.tf")
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
    assert re.search(r'resource_token\s*=\s*"lab5"', main)
    assert "md5(" not in main
    assert "credit-policy-${var.environment_name}" in main
    assert "stcp${local.resource_token}" in main
    assert re.search(
        r'search_name\s*=\s*"credit-policy-\$\{local\.resource_token\}"', main
    )
    assert re.search(
        r'foundry_name\s*=\s*"credit-policy-\$\{local\.resource_token\}"', main
    )
    assert "srch-cp-" not in main
    assert "aif-cp-" not in main
    assert "credit-policy-demo" in main
    storage = _read("storage.tf")
    assert DEFAULT_CONTAINER in storage
    assert "client-applications" in storage
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
    main = _read("main.tf")
    foundry = _read("foundry.tf")
    assert re.search(r"chat_capacity\s*=\s*50", main)
    assert re.search(r"embedding_capacity\s*=\s*20", main)
    assert "capacity = local.chat_capacity" in foundry
    assert "capacity = local.embedding_capacity" in foundry
    assert re.search(r"chat_capacity\s*=\s*50000", main) is None
    assert re.search(r"capacity\s*=\s*50000", foundry) is None


def test_terraform_variables_are_tfvars_keys_only() -> None:
    variables = _read("variables.tf")
    names = re.findall(r'^variable "(\S+)"', variables, re.M)
    assert names == ["environment_name", "location"]
    for dropped in (
        "principal_id",
        "chat_capacity",
        "embedding_capacity",
        "project_name",
        "chat_deployment_name",
        "embedding_deployment_name",
    ):
        assert f'variable "{dropped}"' not in variables
    main = _read("main.tf")
    assert re.search(r'project_name\s*=\s*"credit-policy-demo"', main)
    assert re.search(r'chat_deployment_name\s*=\s*"gpt-5-mini"', main)
    assert re.search(r'embedding_deployment_name\s*=\s*"text-embedding-3-large"', main)
    assert "var.principal_id" not in main
    assert "data.azurerm_client_config.current.object_id" in main


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


def test_environment_name_only_dev1_or_prd1() -> None:
    variables = _read("variables.tf")
    env_block = variables.split('variable "location"', 1)[0]
    assert 'variable "environment_name"' in env_block
    assert "credit-policy-demo" not in env_block
    assert re.search(
        r'contains\(\s*\["dev1",\s*"prd1"\]\s*,\s*var\.environment_name\)', env_block
    )
    assert re.search(r'default\s*=\s*"dev1"', env_block)


def test_tfvars_files_for_dev1_and_prd1() -> None:
    for env in ("dev1", "prd1"):
        text = _read(f"{env}.tfvars")
        assert f'environment_name = "{env}"' in text
        assert "credit-policy-demo" not in text
        assert 'location         = "swedencentral"' in text or re.search(
            r'location\s*=\s*"swedencentral"', text
        )


def test_makefile_env_and_var_file(repo_root: Path) -> None:
    makefile = (repo_root / "Makefile").read_text(encoding="utf-8")
    assert "ENV ?= dev1" in makefile
    assert "ENV ?= credit-policy-demo" not in makefile
    assert "ALLOWED_ENVS := dev1 prd1" in makefile
    assert "-var-file=$(ENV).tfvars" in makefile
    assert "need-env" in makefile
    assert re.search(r"^infra-create:", makefile, re.M)
    assert re.search(r"^infra-plan:", makefile, re.M)
    assert re.search(r"^infra-fmt:", makefile, re.M)
    assert re.search(r"^infra-validate:", makefile, re.M)
    assert re.search(r"^infra-show:", makefile, re.M)
    assert re.search(r"^infra-destroy:", makefile, re.M)
    assert re.search(r"^infra-backend-create:", makefile, re.M)
    assert re.search(r"^infra-backend-show:", makefile, re.M)
    assert re.search(r"^infra-backend-destroy:", makefile, re.M)
    assert re.search(r"^ai-account:", makefile, re.M)
    assert re.search(r"^ai-project:", makefile, re.M)
    assert re.search(r"^ai-agent:", makefile, re.M)
    assert re.search(r"^ai-search:", makefile, re.M)
    assert re.search(r"^ai-storage:", makefile, re.M)
    assert "use gmake infra-create" in makefile
    assert "use gmake infra-backend-create" in makefile


def test_makefile_ai_inspect_recipes(repo_root: Path) -> None:
    makefile = (repo_root / "Makefile").read_text(encoding="utf-8")
    needles = {
        "ai-account": (
            "az cognitiveservices account show",
            "az cognitiveservices account deployment list",
            "properties.provisioningState",
        ),
        "ai-project": ("az cognitiveservices account project show",),
        "ai-agent": (
            "az rest",
            "credit-policy-agent",
            "api-version=v1",
            "--resource https://ai.azure.com",
        ),
        "ai-search": ("az search service show",),
        "ai-storage": (
            "az storage account show",
            "az storage container list",
            "--auth-mode login",
        ),
    }
    start = makefile.index("define ai-pre")
    pre = makefile[start : makefile.index("endef", start)]
    assert "need-az" in pre
    assert "need-az-auth" in pre
    assert "need-jq" in pre
    assert "need-terraform" not in pre
    for name, required in needles.items():
        assert re.search(rf"^{name}:", makefile, re.M)
        recipe = _makefile_recipe(makefile, name)
        assert "$(call ai-pre," in recipe
        assert "need-terraform" not in recipe
        assert "-o table" in recipe
        for needle in required:
            assert needle in recipe, (name, needle)
    assert "infra/outputs.json" in makefile
    assert "jq -r" in makefile
    assert "python3" not in makefile
    assert not re.search(r"^ai-list:", makefile, re.M)
    assert not re.search(r"^ai-show:", makefile, re.M)
    assert "ai-foundry-show" not in makefile
    assert "ai-cognitiveservices" not in makefile


def test_gha_release_uses_prd1_backend_key(repo_root: Path) -> None:
    text = (repo_root / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
    assert "key=prd1.tfstate" in text
    assert "storage_account_name=lab5tfstate1" in text
    assert "ARM_USE_AZUREAD" in text


def test_azurerm_backend_uses_azuread() -> None:
    versions = _read("versions.tf")
    assert 'backend "azurerm"' in versions
    assert "use_azuread_auth" in versions
    assert "terraform-state-shared" in versions
    assert 'container_name      = "tfstate"' in versions or re.search(
        r'container_name\s*=\s*"tfstate"', versions
    )


def test_backend_bootstrap_uses_az_cli_not_terraform(repo_root: Path) -> None:
    assert not (repo_root / "infra" / "backend").exists()
    makefile = (repo_root / "Makefile").read_text(encoding="utf-8")
    assert "terraform -chdir=infra/backend" not in makefile
    create = _makefile_recipe(makefile, "infra-backend-create")
    show = _makefile_recipe(makefile, "infra-backend-show")
    destroy = _makefile_recipe(makefile, "infra-backend-destroy")
    assert "need-terraform" not in create
    assert "need-terraform" not in show
    assert "need-terraform" not in destroy
    assert "az group create" in create
    assert "az storage account create" in create
    assert "az storage container create" in create
    assert "Storage Blob Data Contributor" in create
    assert "TFSTATE_ACCOUNT := lab5tfstate1" in makefile
    assert "stcp${" not in makefile
    assert "az group show" in show
    assert "az storage account show" in show
    assert "az storage account delete" in destroy
    assert "az group delete" not in destroy
    assert "TFSTATE_RG := terraform-state-shared" in makefile
    gitignore = (repo_root / ".gitignore").read_text(encoding="utf-8")
    assert "*.tfstate" in gitignore
    assert "*.tfstate.*" in gitignore
    assert "infra/outputs.json" in gitignore


def test_tfstate_account_name_is_fixed(repo_root: Path) -> None:
    makefile = (repo_root / "Makefile").read_text(encoding="utf-8")
    match = re.search(r"^TFSTATE_ACCOUNT := (\S+)", makefile, re.M)
    assert match is not None
    name = match.group(1)
    assert name == "lab5tfstate1"
    assert not name.startswith("stcp")
    assert 3 <= len(name) <= 24
    assert name.isalnum() and name.islower()


def test_makefile_reconfigure_and_backend_key(repo_root: Path) -> None:
    makefile = (repo_root / "Makefile").read_text(encoding="utf-8")
    init = _makefile_recipe(makefile, "infra-init")
    assert "-reconfigure" in init
    assert "-migrate-state" not in makefile
    assert "key=$(ENV).tfstate" in makefile
    assert "lab5tfstate1" in makefile
    assert "terraform-state-shared" in makefile


def test_makefile_infra_create_emits_outputs_json(repo_root: Path) -> None:
    makefile = (repo_root / "Makefile").read_text(encoding="utf-8")
    create = _makefile_recipe(makefile, "infra-create")
    destroy = _makefile_recipe(makefile, "infra-destroy")
    assert "terraform -chdir=infra output -json > infra/outputs.json" in create
    assert "rm -f infra/outputs.json" in destroy
    assert "terraform output" not in destroy


def test_makefile_infra_plan(repo_root: Path) -> None:
    makefile = (repo_root / "Makefile").read_text(encoding="utf-8")
    plan = _makefile_recipe(makefile, "infra-plan")
    assert "terraform -chdir=infra plan" in plan
    assert "-var-file=$(ENV).tfvars" in plan
    assert "outputs.json" not in plan
    assert "auto-approve" not in plan
    assert "infra-plan: infra-validate" in makefile


def test_makefile_infra_fmt_and_validate(repo_root: Path) -> None:
    makefile = (repo_root / "Makefile").read_text(encoding="utf-8")
    fmt = _makefile_recipe(makefile, "infra-fmt")
    validate = _makefile_recipe(makefile, "infra-validate")
    assert "terraform -chdir=infra fmt" in fmt
    assert "need-terraform" in fmt
    assert "infra-init" not in fmt
    assert "-var-file" not in fmt
    assert "terraform -chdir=infra validate" in validate
    assert "-var-file" not in validate
    assert "auto-approve" not in fmt
    assert "auto-approve" not in validate
    assert re.search(r"^infra-fmt:", makefile, re.M)
    assert "infra-init: infra-fmt" in makefile
    assert "infra-validate: infra-init" in makefile
    assert "infra-plan: infra-validate" in makefile
    assert "infra-create: infra-validate" in makefile
    assert "infra-destroy: infra-init" in makefile


def test_gha_deploy_writes_outputs_json(repo_root: Path) -> None:
    text = (repo_root / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
    assert "terraform -chdir=infra output -json > infra/outputs.json" in text


def test_storage_public_network_access_is_enabled_string() -> None:
    storage = _read("storage.tf")
    assert re.search(r'public_network_access\s*=\s*"Enabled"', storage)
    assert "public_network_access_enabled" not in storage


def test_search_and_foundry_keep_bool_public_network_access() -> None:
    search = _read("search.tf")
    foundry = _read("foundry.tf")
    assert re.search(r"public_network_access_enabled\s*=\s*true", search)
    assert re.search(r"public_network_access_enabled\s*=\s*true", foundry)
    assert not re.search(r"public_network_access\s*=", search)
    assert not re.search(r"public_network_access\s*=", foundry)


def test_azurerm_provider_version_supports_storage_public_network_access() -> None:
    versions = _read("versions.tf")
    assert re.search(r'version\s*=\s*">=\s*5\.5\.0"', versions)
