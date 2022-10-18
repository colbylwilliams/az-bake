# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

from azure.cli.core.azclierror import ValidationError
from azure.cli.core.commands.client_factory import get_subscription_id
from azure.cli.core.commands.parameters import get_resources_in_resource_group
from azure.mgmt.core.tools import is_valid_resource_id, resource_id

from ._arm import get_resource_group_tags
from ._client_factory import cf_msi, cf_network
from ._constants import tag_key
from ._utils import get_logger

logger = get_logger(__name__)


def get_sandbox_from_group(cmd, resource_group_name):
    tags = get_resource_group_tags(cmd, resource_group_name)

    sub = tags.get(tag_key('subscription'))
    loc = tags.get(tag_key('location'))
    identity_id = tags.get(tag_key('identityId'))
    keyvault_name = tags.get(tag_key('keyVault'))
    storage_account = tags.get(tag_key('storageAccount'))
    vnet_name = tags.get(tag_key('virtualNetwork'))
    vnet_group = tags.get(tag_key('virtualNetworkResourceGroup'))
    default_subnet = tags.get(tag_key('defaultSubnet'))
    builder_subnet = tags.get(tag_key('builderSubnet'))

    if not sub:
        sub = get_subscription_id(cmd.cli_ctx)

    # if not loc:
    #     loc = get_default_location_from_sandbox_resource_group(cmd, ns)

    if not identity_id or not keyvault_name or not storage_account or not vnet_name:
        resources = get_resources_in_resource_group(cmd.cli_ctx, resource_group_name)

    # check for identity
    if not identity_id:
        identity = next((r for r in resources if r.type == 'Microsoft.ManagedIdentity/userAssignedIdentities'), None)
        if not identity:
            raise ValidationError('No identity found in sandbox resource group')
        identity_id = identity.id

    if not is_valid_resource_id(identity_id):
        raise ValidationError('Invalid identity id. Must be a resource id')

    # if gallery_resource_id:
    #     identity_id = ensure_gallery_permissions(cmd, gallery_resource_id, identity_id)

    # TODO: Also check for resource, keyvault, and storage account permissions

    # check for keyvault
    if not keyvault_name:
        keyvault = next((r for r in resources if r.type == 'Microsoft.KeyVault/vaults'), None)
        if not keyvault:
            raise ValidationError('Could not find keyvault in sandbox resource group')
        keyvault_name = keyvault.name

    # check for storage
    if not storage_account:
        storage = next((r for r in resources if r.type == 'Microsoft.Storage/storageAccounts'), None)
        if not storage:
            raise ValidationError('Could not find storage in sandbox resource group')
        storage_account = storage.name

    # check for vnet
    if not vnet_name:
        vnet = next((r for r in resources if r.type == 'Microsoft.Network/virtualNetworks'), None)
        if not vnet:
            raise ValidationError('Could not find vnet in sandbox resource group')
        vnet_name = vnet.name

    if not default_subnet or not builder_subnet:
        net_client = cf_network(cmd.cli_ctx).virtual_networks
        vnet = net_client.get(resource_group_name, vnet_name)

        # check for builders subnet
        delegated_subnets = [s for s in vnet.subnets if s.delegations and
                             any([d for d in s.delegations if d.service_name == 'Microsoft.ContainerInstance/containerGroups'])]
        if not delegated_subnets:
            raise ValidationError('Could not find builders subnet (delegated to ACI) in vnet')
        if len(delegated_subnets) > 1:
            raise ValidationError('Found more than one subnet delegated to ACI in vnet. '
                                  'Cant determine which subnet to use for builders.')
        builder_subnet = delegated_subnets[0]

        # check for default subnet
        other_subnets = [s for s in vnet.subnets if s.id != builder_subnet.id]
        if not other_subnets:
            raise ValidationError('Could not find a default subnet in vnet')
        if len(other_subnets) > 1:
            raise ValidationError('Found more than one subnet (not delegated to ACI) in vnet. '
                                  'Cant determine which subnet to use for default.')
        default_subnet = other_subnets[0]

        default_subnet = default_subnet.name
        builder_subnet = builder_subnet.name

    return {
        'resourceGroup': resource_group_name,
        'subscription': sub,
        'location': loc,
        'virtualNetwork': vnet_name,
        'virtualNetworkResourceGroup': vnet_group or resource_group_name,
        'defaultSubnet': default_subnet,
        'builderSubnet': builder_subnet,
        'keyVault': keyvault_name,
        'storageAccount': storage_account,
        'identityId': identity_id
    }


def get_builder_subnet_id(sandbox):
    for k in ['subscription', 'virtualNetworkResourceGroup', 'virtualNetwork', 'builderSubnet']:
        if k not in sandbox or not sandbox[k]:
            raise ValidationError(f'Sandbox is missing required property: {k}')
    return resource_id(subscription=sandbox['subscription'], resource_group=sandbox['virtualNetworkResourceGroup'],
                       namespace='Microsoft.Network', type='virtualNetworks', name=sandbox['virtualNetwork'],
                       child_type_1='subnets', child_name_1=sandbox['builderSubnet'])
