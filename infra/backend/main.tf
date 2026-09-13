data "azurerm_client_config" "current" {}

locals {
  # Prefix sttfst, never workload stcp*.
  storage_name = "sttfst${substr(md5("${data.azurerm_client_config.current.subscription_id}-tfstate"), 0, 13)}"
  operator_principal_id = (
    var.principal_id != "" ? var.principal_id : data.azurerm_client_config.current.object_id
  )
  storage_blob_data_contributor = "ba92f5b4-2d11-453d-a403-e96b0029c9fe"
  role_definition_prefix        = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions"
  tags = {
    environment = "tfstate"
    project     = "credit-policy-agent"
  }
}

resource "azurerm_resource_group" "tfstate" {
  name     = "rg-credit-policy-tfstate"
  location = var.location
  tags     = local.tags
}

resource "azurerm_storage_account" "tfstate" {
  name                            = local.storage_name
  resource_group_name             = azurerm_resource_group.tfstate.name
  location                        = azurerm_resource_group.tfstate.location
  account_kind                    = "StorageV2"
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  https_traffic_only_enabled      = true
  public_network_access_enabled   = true
  access_tier                     = "Hot"
  tags                            = local.tags
}

resource "azurerm_storage_container" "tfstate" {
  name                  = "tfstate"
  storage_account_id    = azurerm_storage_account.tfstate.id
  container_access_type = "private"
}

resource "azurerm_role_assignment" "operator_blob_contributor" {
  scope              = azurerm_storage_account.tfstate.id
  role_definition_id = "${local.role_definition_prefix}/${local.storage_blob_data_contributor}"
  principal_id       = local.operator_principal_id
}
