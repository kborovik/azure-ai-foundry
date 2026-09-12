@description('Storage account name. Must be 3-24 lowercase alphanumeric characters.')
@minLength(3)
@maxLength(24)
param name string

@description('Azure region for the storage account.')
param location string

@description('Blob container that holds generated credit-policy Markdown.')
param containerName string = 'credit-policies'

@description('Resource tags.')
param tags object = {}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: name
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  tags: tags
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: 'Enabled'
    accessTier: 'Hot'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource container 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: containerName
  properties: {
    publicAccess: 'None'
  }
}

output name string = storage.name
output id string = storage.id
output accountUrl string = 'https://${storage.name}.blob.${environment().suffixes.storage}'
output containerName string = container.name
