@description('Storage account name (existing in this resource group).')
param storageAccountName string

@description('Azure AI Search service name (existing in this resource group).')
param searchServiceName string

@description('Foundry (AIServices) account name (existing in this resource group).')
param foundryAccountName string

@description('Foundry project name (existing under the Foundry account).')
param foundryProjectName string

@description('Search service system-assigned principal ID.')
param searchPrincipalId string

@description('Foundry project system-assigned principal ID (MCP authenticates as this identity).')
param projectPrincipalId string

@description('Deploying user or app principal from azd (AZURE_PRINCIPAL_ID). Empty skips operator assignments.')
param principalId string = ''

var storageBlobDataReader = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
var storageBlobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var cognitiveServicesUser = 'a97b65f3-24c7-4388-baec-2e87135dc908'
var searchIndexDataReader = '1407120a-92aa-4202-b7e9-c0e197c71c8f'
var searchServiceContributor = '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
var searchIndexDataContributor = '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
var foundryUser = '53ca6127-db72-4b80-b1b0-d745d6d5456d'
var foundryProjectManager = 'eadc314b-1a2d-4efa-be10-5d325db5065e'

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource search 'Microsoft.Search/searchServices@2025-05-01' existing = {
  name: searchServiceName
}

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' existing = {
  parent: foundry
  name: foundryProjectName
}

resource searchReadsBlobs 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, searchPrincipalId, storageBlobDataReader)
  scope: storage
  properties: {
    principalId: searchPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataReader)
    principalType: 'ServicePrincipal'
  }
}

resource searchUsesFoundry 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, searchPrincipalId, cognitiveServicesUser)
  scope: foundry
  properties: {
    principalId: searchPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUser)
    principalType: 'ServicePrincipal'
  }
}

resource projectReadsSearch 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, projectPrincipalId, searchIndexDataReader)
  scope: search
  properties: {
    principalId: projectPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexDataReader)
    principalType: 'ServicePrincipal'
  }
}

resource operatorBlobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(storage.id, principalId, storageBlobDataContributor)
  scope: storage
  properties: {
    principalId: principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributor)
  }
}

resource operatorSearchContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(search.id, principalId, searchServiceContributor)
  scope: search
  properties: {
    principalId: principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchServiceContributor)
  }
}

resource operatorSearchIndexContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(search.id, principalId, searchIndexDataContributor)
  scope: search
  properties: {
    principalId: principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexDataContributor)
  }
}

resource operatorFoundryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(foundry.id, principalId, foundryUser)
  scope: foundry
  properties: {
    principalId: principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryUser)
  }
}

resource operatorFoundryProjectManager 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(foundryProject.id, principalId, foundryProjectManager)
  scope: foundryProject
  properties: {
    principalId: principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryProjectManager)
  }
}
