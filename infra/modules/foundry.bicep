@description('Microsoft Foundry (AIServices) account name and custom subdomain.')
param name string

@description('Azure region for the Foundry resource and model deployments.')
param location string

@description('Foundry project name.')
param projectName string = 'credit-policy-demo'

@description('Chat model deployment name and model name.')
param chatDeploymentName string = 'gpt-5-mini'

@description('Chat deployment SKU capacity. Foundry Models sku.capacity 1 = 1000 TPM; 50 = 50k TPM.')
@minValue(1)
param chatCapacity int = 50

@description('Embedding model deployment name and model name.')
param embeddingDeploymentName string = 'text-embedding-3-large'

@description('Embedding deployment SKU capacity (1 = 1000 TPM).')
@minValue(1)
param embeddingCapacity int = 20

@description('Resource tags.')
param tags object = {}

var foundryEndpoint = 'https://${name}.services.ai.azure.com'

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: name
  location: location
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  tags: tags
  properties: {
    customSubDomainName: name
    publicNetworkAccess: 'Enabled'
    allowProjectManagement: true
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: projectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  tags: tags
  properties: {
    displayName: projectName
    description: 'Contoso Demo Bank credit policy agent'
  }
}

resource chatDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: chatDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: chatCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5-mini'
      version: '2025-08-07'
    }
  }
}

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: embeddingDeploymentName
  dependsOn: [
    chatDeployment
  ]
  sku: {
    name: 'Standard'
    capacity: embeddingCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-large'
      version: '1'
    }
  }
}

output name string = account.name
output id string = account.id
output endpoint string = foundryEndpoint
output projectName string = project.name
output projectId string = project.id
output projectEndpoint string = '${foundryEndpoint}/api/projects/${project.name}'
output projectPrincipalId string = project.identity.principalId
output chatDeploymentName string = chatDeployment.name
output embeddingDeploymentName string = embeddingDeployment.name
