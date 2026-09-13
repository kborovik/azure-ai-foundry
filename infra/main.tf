data "azurerm_client_config" "current" {}

locals {
  resource_token            = "lab5"
  resource_group_name       = "rg-credit-policy-${var.environment_name}"
  storage_name              = "stcp${local.resource_token}"
  search_name               = "credit-policy-${local.resource_token}"
  foundry_name              = "credit-policy-${local.resource_token}"
  operator_principal_id     = data.azurerm_client_config.current.object_id
  project_name              = "credit-policy-demo"
  chat_deployment_name      = "gpt-5-mini"
  embedding_deployment_name = "text-embedding-3-large"
  chat_capacity             = 50
  embedding_capacity        = 20
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
