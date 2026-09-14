data "azurerm_client_config" "current" {}

locals {
  tags = {
    environment = var.environment_name
    project     = "credit-policy-agent"
  }
}

resource "azurerm_resource_group" "rg" {
  name     = "credit-policy-${var.environment_name}"
  location = var.location
  tags     = local.tags
}
