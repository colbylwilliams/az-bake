// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

@minLength(36)
@maxLength(36)
@description('The principal id of the Service Principal to assign permissions to the Gallery.')
param principalId string

@allowed([ 'Reader', 'Contributor', 'Owner' ])
@description('The Role to assign.')
param role string = 'Reader'

@allowed([ 'Device', 'ForeignGroup', 'Group', 'ServicePrincipal', 'User' ])
@description('The principal type of the assigned principal ID.')
param principalType string = 'ServicePrincipal'

var assignmentId = guid('group${role}${resourceGroup().id}$${principalId}')

// docs: https://docs.microsoft.com/en-us/azure/role-based-access-control/built-in-roles#reader
var readerRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'acdd72a7-3385-48ef-bd42-f606fba81ae7')
// docs: https://docs.microsoft.com/en-us/azure/role-based-access-control/built-in-roles#contributor
var contributorRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b24988ac-6180-42a0-ab88-20f7382dd24c')
// docs: https://docs.microsoft.com/en-us/azure/role-based-access-control/built-in-roles#owner
var ownerRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8e3af657-a8ff-443c-a75c-2fe8c4bcb635')

var roleDefinitionId = role == 'Owner' ? ownerRoleId : role == 'Contributor' ? contributorRoleId : readerRoleId

resource groupAssignmentId 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: assignmentId
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: roleDefinitionId
  }
  scope: resourceGroup()
}
