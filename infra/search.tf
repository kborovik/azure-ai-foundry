resource "azurerm_search_service" "search" {
  name                          = "credit-policy-1"
  resource_group_name           = azurerm_resource_group.rg.name
  location                      = azurerm_resource_group.rg.location
  sku                           = "basic"
  replica_count                 = 1
  partition_count               = 1
  semantic_search_sku           = "free"
  public_network_access_enabled = true
  local_authentication_enabled  = true
  authentication_failure_mode   = "http401WithBearerChallenge"
  tags                          = local.tags

  identity {
    type = "SystemAssigned"
  }
}
