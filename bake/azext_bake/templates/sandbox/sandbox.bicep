// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

@description('Location for the resources. If none is provided, the resource group location is used.')
param location string = resourceGroup().location

@description('Name for the created KeyVault')
param keyVaultName string

@description('Name for the created Storage Account')
param storageName string

@description('Name for the created Virtual Network')
param vnetName string

@description('Name for the created Managed Identity')
param identityName string

@description('The principal id of a service principal used in the CI pipeline. It will be givin contributor role to the resource group.')
param ciPrincipalId string = ''

param vnetAddressPrefixes array = [ '10.0.0.0/24' ] // 256 addresses

param defaultSubnetName string = 'default'
param defaultSubnetAddressPrefix string = '10.0.0.0/25' // 123 + 5 Azure reserved addresses

param builderSubnetName string = 'builders'
param builderSubnetAddressPrefix string = '10.0.0.128/25' // 123 + 5 Azure reserved addresses

param galleryIds array = []

@description('Tags to be applied to all created resources.')
param tags object = {}

resource builderIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2022-01-31-preview' = {
  name: identityName
  location: location
  tags: tags
}

// give builder Contributor on sandbox resoruce group
module builderGroupRole 'groupRoles.bicep' = {
  name: guid(builderIdentity.id, resourceGroup().id, 'Contributor')
  params: {
    role: 'Contributor'
    principalId: builderIdentity.properties.principalId
  }
  scope: resourceGroup()
}

// give builder Contributor on gallery resoruce groups
module galleryRoles 'groupRoles.bicep' = [for galleryId in galleryIds: if (!empty(galleryIds)) {
  name: guid(builderIdentity.id, galleryId, 'Contributor')
  params: {
    role: 'Contributor'
    principalId: builderIdentity.properties.principalId
  }
  scope: resourceGroup(first(split(last(split(replace(galleryId, 'resourceGroups', 'resourcegroups'), '/resourcegroups/')), '/')))
}]

// give CI pricipal Contributor on sandbox resoruce group
module ciGroupRole 'groupRoles.bicep' = if (!empty(ciPrincipalId)) {
  name: guid(ciPrincipalId, resourceGroup().id, 'Contributor')
  params: {
    role: 'Contributor'
    principalId: ciPrincipalId
  }
  scope: resourceGroup()
}

resource vnet 'Microsoft.Network/virtualNetworks@2021-03-01' = {
  name: vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: vnetAddressPrefixes
    }
    subnets: [
      {
        name: defaultSubnetName
        properties: {
          addressPrefix: defaultSubnetAddressPrefix
          privateEndpointNetworkPolicies: 'Disabled'
          privateLinkServiceNetworkPolicies: 'Enabled'
        }
      }
      {
        name: builderSubnetName
        properties: {
          addressPrefix: builderSubnetAddressPrefix
          privateEndpointNetworkPolicies: 'Disabled'
          privateLinkServiceNetworkPolicies: 'Enabled'
          serviceEndpoints: [
            { service: 'Microsoft.Storage', locations: [ location ] }
            { service: 'Microsoft.KeyVault', locations: [ '*' ] }
            { service: 'Microsoft.AzureActiveDirectory', locations: [ '*' ] }
          ]
          delegations: [
            {
              name: 'Microsoft.ContainerInstance/containerGroups'
              properties: { serviceName: 'Microsoft.ContainerInstance/containerGroups' }
            }
          ]
        }
      }
    ]
  }
  tags: tags
}

resource keyVault 'Microsoft.KeyVault/vaults@2022-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    enabledForDeployment: true
    enabledForTemplateDeployment: true
    enabledForDiskEncryption: false
    enableRbacAuthorization: true
    // TODO: uncomment this
    // enablePurgeProtection: true
    // enableSoftDelete: true
    // softDeleteRetentionInDays: 90
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Deny'
    }
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: tenant().tenantId
  }
  tags: tags
}

resource builderKeyVaultAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid('kvsecretofficer${resourceGroup().id}${keyVaultName}${identityName}')
  properties: {
    principalId: builderIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    // docs: https://docs.microsoft.com/en-us/azure/role-based-access-control/built-in-roles#key-vault-secrets-officer
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7')
  }
  scope: keyVault
}

resource storage 'Microsoft.Storage/storageAccounts@2021-09-01' = {
  name: storageName
  location: location
  sku: {
    name: 'Standard_ZRS'
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Deny'
      virtualNetworkRules: [
        {
          id: '${vnet.id}/subnets/${builderSubnetName}'
          action: 'Allow'
        }
      ]
    }
  }
  tags: tags
}

resource privateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.vaultcore.azure.net'
  location: 'global'
  tags: tags

  resource privateDnsZoneLink 'virtualNetworkLinks' = {
    name: '${vnet.name}-dnslink'
    location: 'global'
    properties: {
      registrationEnabled: false
      virtualNetwork: { id: vnet.id }
    }
    tags: tags
  }
}

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2022-01-01' = {
  name: '${vnet.name}-pe-${defaultSubnetName}'
  location: location
  properties: {
    subnet: {
      id: '${vnet.id}/subnets/${defaultSubnetName}'
    }
    privateLinkServiceConnections: [
      {
        name: '${vnet.name}-pe-${defaultSubnetName}-kv'
        properties: {
          privateLinkServiceId: keyVault.id
          groupIds: [ 'vault' ]
        }
      }
    ]
  }
  tags: tags

  resource privateDnsZoneGroup 'privateDnsZoneGroups' = {
    name: '${vnet.name}-pe-${defaultSubnetName}-dnsgroup'
    properties: {
      privateDnsZoneConfigs: [
        {
          name: 'privatelink.vaultcore.azure.net'
          properties: {
            privateDnsZoneId: privateDnsZone.id
          }
        }
      ]
    }
  }
}

resource group_tags 'Microsoft.Resources/tags@2021-04-01' = {
  name: 'default'
  properties: {
    tags: union({
        'hidden-bake:location': location
        'hidden-bake:resourceGroup': resourceGroup().name
        'hidden-bake:subscription': az.subscription().subscriptionId
        'hidden-bake:virtualNetwork': vnet.name
        'hidden-bake:virtualNetworkResourceGroup': resourceGroup().name
        'hidden-bake:defaultSubnet': defaultSubnetName
        'hidden-bake:builderSubnet': builderSubnetName
        'hidden-bake:keyVault': keyVault.name
        'hidden-bake:storageAccount': storage.name
        'hidden-bake:identityId': builderIdentity.id
      }, tags)
  }
}
