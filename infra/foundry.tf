resource "azurerm_cognitive_account" "foundry" {
  name                          = "credit-policy-lab5"
  resource_group_name           = azurerm_resource_group.rg.name
  location                      = azurerm_resource_group.rg.location
  kind                          = "AIServices"
  sku_name                      = "S0"
  custom_subdomain_name         = "credit-policy-lab5"
  project_management_enabled    = true
  public_network_access_enabled = true
  local_auth_enabled            = true
  tags                          = local.tags

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_cognitive_account_project" "project" {
  name                 = "credit-policy-demo"
  cognitive_account_id = azurerm_cognitive_account.foundry.id
  location             = azurerm_resource_group.rg.location
  display_name         = "credit-policy-demo"
  description          = "Contoso Demo Bank credit policy agent"
  tags                 = local.tags

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_cognitive_deployment" "chat" {
  name                 = "gpt-5-mini"
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  model {
    format  = "OpenAI"
    name    = "gpt-5-mini"
    version = "2025-08-07"
  }

  sku {
    name     = "GlobalStandard"
    capacity = 50
  }
}

resource "azurerm_cognitive_deployment" "embedding" {
  name                 = "text-embedding-3-large"
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  model {
    format  = "OpenAI"
    name    = "text-embedding-3-large"
    version = "1"
  }

  sku {
    name     = "Standard"
    capacity = 20
  }

  depends_on = [azurerm_cognitive_deployment.chat]
}
