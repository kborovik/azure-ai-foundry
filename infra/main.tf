data "azurerm_client_config" "current" {}

locals {
  resource_token      = substr(md5("${data.azurerm_client_config.current.subscription_id}-${var.environment_name}-${var.location}"), 0, 13)
  resource_group_name = "rg-credit-policy-${var.environment_name}"
  storage_name        = "stcp${local.resource_token}"
  search_name         = "srch-cp-${local.resource_token}"
  foundry_name        = "aif-cp-${local.resource_token}"
  operator_principal_id = (
    var.principal_id != "" ? var.principal_id : data.azurerm_client_config.current.object_id
  )
  tags = {
    environment = var.environment_name
    project     = "credit-policy-agent"
  }
}

resource "azurerm_resource_group" "rg" {
  name     = local.resource_group_name
  location = var.location
  tags     = local.tags
}
