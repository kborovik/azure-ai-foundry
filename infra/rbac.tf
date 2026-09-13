locals {
  storage_blob_data_reader      = "2a2b9908-6ea1-4ae2-8e65-a410df84e7d1"
  storage_blob_data_contributor = "ba92f5b4-2d11-453d-a403-e96b0029c9fe"
  cognitive_services_user       = "a97b65f3-24c7-4388-baec-2e87135dc908"
  search_index_data_reader      = "1407120a-92aa-4202-b7e9-c0e197c71c8f"
  search_service_contributor    = "7ca78c08-252a-4471-8644-bb5ff32d4ba0"
  search_index_data_contributor = "8ebe5a00-799e-43f5-93ac-243d3dce84a7"
  foundry_user                  = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
  foundry_project_manager       = "eadc314b-1a2d-4efa-be10-5d325db5065e"
  role_definition_prefix        = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions"
}

resource "azurerm_role_assignment" "search_reads_blobs" {
  scope                            = azurerm_storage_account.storage.id
  role_definition_id               = "${local.role_definition_prefix}/${local.storage_blob_data_reader}"
  principal_id                     = azurerm_search_service.search.identity[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "search_uses_foundry" {
  scope                            = azurerm_cognitive_account.foundry.id
  role_definition_id               = "${local.role_definition_prefix}/${local.cognitive_services_user}"
  principal_id                     = azurerm_search_service.search.identity[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "project_reads_search" {
  scope                            = azurerm_search_service.search.id
  role_definition_id               = "${local.role_definition_prefix}/${local.search_index_data_reader}"
  principal_id                     = azurerm_cognitive_account_project.project.identity[0].principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "operator_blob_contributor" {
  scope              = azurerm_storage_account.storage.id
  role_definition_id = "${local.role_definition_prefix}/${local.storage_blob_data_contributor}"
  principal_id       = local.operator_principal_id
}

resource "azurerm_role_assignment" "operator_search_contributor" {
  scope              = azurerm_search_service.search.id
  role_definition_id = "${local.role_definition_prefix}/${local.search_service_contributor}"
  principal_id       = local.operator_principal_id
}

resource "azurerm_role_assignment" "operator_search_index_contributor" {
  scope              = azurerm_search_service.search.id
  role_definition_id = "${local.role_definition_prefix}/${local.search_index_data_contributor}"
  principal_id       = local.operator_principal_id
}

resource "azurerm_role_assignment" "operator_foundry_user" {
  scope              = azurerm_cognitive_account.foundry.id
  role_definition_id = "${local.role_definition_prefix}/${local.foundry_user}"
  principal_id       = local.operator_principal_id
}

resource "azurerm_role_assignment" "operator_foundry_project_manager" {
  scope              = azurerm_cognitive_account_project.project.id
  role_definition_id = "${local.role_definition_prefix}/${local.foundry_project_manager}"
  principal_id       = local.operator_principal_id
}
