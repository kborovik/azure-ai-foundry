@description('Azure AI Search service name.')
@minLength(2)
@maxLength(60)
param name string

@description('Azure region for the search service. Must support new Basic services (not eastus/eastus2/westus/westus3) and GlobalStandard gpt-5-mini (not westus2).')
param location string

@description('Resource tags.')
param tags object = {}

resource search 'Microsoft.Search/searchServices@2025-05-01' = {
  name: name
  location: location
  sku: {
    name: 'basic'
  }
  identity: {
    type: 'SystemAssigned'
  }
  tags: tags
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'Default'
    publicNetworkAccess: 'Enabled'
    semanticSearch: 'free'
    authOptions: {
      aadOrApiKey: {
        aadAuthFailureMode: 'http401WithBearerChallenge'
      }
    }
  }
}

output name string = search.name
output id string = search.id
output endpoint string = 'https://${search.name}.search.windows.net'
output principalId string = search.identity.principalId
