output "AZURE_LOCATION" {
  value = var.location
}

output "AZURE_RESOURCE_GROUP" {
  value = azurerm_resource_group.rg.name
}

output "AZURE_STORAGE_ACCOUNT_URL" {
  value = trimsuffix(azurerm_storage_account.storage.primary_blob_endpoint, "/")
}

output "AZURE_STORAGE_RESOURCE_ID" {
  value = azurerm_storage_account.storage.id
}

output "AZURE_SEARCH_ENDPOINT" {
  value = "https://${azurerm_search_service.search.name}.search.windows.net"
}

output "AZURE_AI_PROJECT_ENDPOINT" {
  value = "https://${azurerm_cognitive_account.foundry.name}.services.ai.azure.com/api/projects/${azurerm_cognitive_account_project.project.name}"
}

output "AZURE_AI_PROJECT_RESOURCE_ID" {
  value = azurerm_cognitive_account_project.project.id
}

output "AZURE_AI_SERVICES_ENDPOINT" {
  value = "https://${azurerm_cognitive_account.foundry.name}.services.ai.azure.com"
}

output "AZURE_AI_PROJECT_PRINCIPAL_ID" {
  value = azurerm_cognitive_account_project.project.identity[0].principal_id
}
