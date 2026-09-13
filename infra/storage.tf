resource "azurerm_storage_account" "storage" {
  name                            = local.storage_name
  resource_group_name             = azurerm_resource_group.rg.name
  location                        = azurerm_resource_group.rg.location
  account_kind                    = "StorageV2"
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  https_traffic_only_enabled      = true
  public_network_access           = "Enabled"
  access_tier                     = "Hot"
  tags                            = local.tags
}

resource "azurerm_storage_container" "policies" {
  name                  = "credit-policies"
  storage_account_id    = azurerm_storage_account.storage.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "applications" {
  name                  = "client-applications"
  storage_account_id    = azurerm_storage_account.storage.id
  container_access_type = "private"
}
