targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('azd environment name. Used in the resource group name rg-credit-policy-<env>.')
param environmentName string

@allowed([
  'swedencentral'
  'uksouth'
  'francecentral'
  'canadaeast'
  'centralus'
])
@description('Azure region. Default swedencentral. Blocked: eastus/eastus2/westus/westus3 (no new Search) and westus2 (no GlobalStandard gpt-5-mini).')
param location string = 'swedencentral'

@description('Object ID of the deploying user or app (azd AZURE_PRINCIPAL_ID). Empty skips operator RBAC.')
param principalId string = ''

@description('Chat deployment SKU capacity. 1 = 1000 TPM; default 50 = 50k TPM. Do not set 50000.')
@minValue(1)
@maxValue(1000)
param chatCapacity int = 50

@description('Embedding deployment SKU capacity. 1 = 1000 TPM; default 20 = 20k TPM.')
@minValue(1)
@maxValue(1000)
param embeddingCapacity int = 20

var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = {
  'azd-env-name': environmentName
  project: 'credit-policy-agent'
}

var resourceGroupName = 'rg-credit-policy-${environmentName}'
var storageName = 'stcp${resourceToken}'
var searchName = 'srch-cp-${resourceToken}'
var foundryName = 'aif-cp-${resourceToken}'
var projectName = 'credit-policy-demo'
var containerName = 'credit-policies'

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

module storage 'modules/storage.bicep' = {
  name: 'storage'
  scope: rg
  params: {
    name: storageName
    location: location
    containerName: containerName
    tags: tags
  }
}

module search 'modules/search.bicep' = {
  name: 'search'
  scope: rg
  params: {
    name: searchName
    location: location
    tags: tags
  }
}

module foundry 'modules/foundry.bicep' = {
  name: 'foundry'
  scope: rg
  params: {
    name: foundryName
    location: location
    projectName: projectName
    chatCapacity: chatCapacity
    embeddingCapacity: embeddingCapacity
    tags: tags
  }
}

module rbac 'modules/rbac.bicep' = {
  name: 'rbac'
  scope: rg
  params: {
    storageAccountName: storage.outputs.name
    searchServiceName: search.outputs.name
    foundryAccountName: foundry.outputs.name
    foundryProjectName: foundry.outputs.projectName
    searchPrincipalId: search.outputs.principalId
    projectPrincipalId: foundry.outputs.projectPrincipalId
    principalId: principalId
  }
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_STORAGE_ACCOUNT_URL string = storage.outputs.accountUrl
output AZURE_STORAGE_RESOURCE_ID string = storage.outputs.id
output AZURE_SEARCH_ENDPOINT string = search.outputs.endpoint
output AZURE_AI_PROJECT_ENDPOINT string = foundry.outputs.projectEndpoint
output AZURE_AI_PROJECT_RESOURCE_ID string = foundry.outputs.projectId
output AZURE_AI_SERVICES_ENDPOINT string = foundry.outputs.endpoint
output AZURE_AI_PROJECT_PRINCIPAL_ID string = foundry.outputs.projectPrincipalId
