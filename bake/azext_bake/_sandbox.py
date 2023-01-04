# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------
# pylint: disable=logging-fstring-interpolation

from azure.cli.core.azclierror import ValidationError
from azure.cli.core.commands.client_factory import get_subscription_id
from azure.cli.core.commands.parameters import get_resources_in_resource_group
from azure.cli.core.profiles import ResourceType
from azure.mgmt.core.tools import is_valid_resource_id, resource_id

from ._arm import get_resource_group_tags
from ._client_factory import cf_keyvault, cf_network, cf_storage
from ._constants import tag_key
from ._data import Sandbox
from ._utils import get_logger

logger = get_logger(__name__)


def get_sandbox_from_group(cmd, resource_group_name: str) -> Sandbox:  # pylint: disable=too-many-statements
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
            raise ValidationError('No identity found in sandbox resource group.\n'
                                  'If are moving from a previous version of the dev-box-images repo, '
                                  'please run "az bake sandbox create" to create a new sandbox.')
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
                             any(d for d in s.delegations
                                 if d.service_name == 'Microsoft.ContainerInstance/containerGroups')]
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

    return Sandbox({
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
    })


def get_builder_subnet_id(sandbox: Sandbox):
    # for k in ['subscription', 'virtualNetworkResourceGroup', 'virtualNetwork', 'builderSubnet']:
    #     if k not in sandbox or not sandbox[k]:
    #         raise ValidationError(f'Sandbox is missing required property: {k}')
    return resource_id(subscription=sandbox.subscription, resource_group=sandbox.virtual_network_resource_group,
                       namespace='Microsoft.Network', type='virtualNetworks', name=sandbox.virtual_network,
                       child_type_1='subnets', child_name_1=sandbox.builder_subnet)


def _check_keyvault_name_availability(cmd, keyvault_name):
    kv_name = keyvault_name
    vaults_client = cf_keyvault(cli_ctx=cmd.cli_ctx).vaults
    VaultCheckNameAvailabilityParameters = cmd.get_models('VaultCheckNameAvailabilityParameters',
                                                          resource_type=ResourceType.MGMT_KEYVAULT,
                                                          operation_group='vaults')

    logger.info(f'Checking availability of KeyVault name: {kv_name}')
    name_availability = vaults_client.check_name_availability(VaultCheckNameAvailabilityParameters(name=kv_name))

    counter = 0
    while name_availability.name_available is False:
        logger.info(f'KeyVault name not available: {kv_name}')
        if counter > 9:
            raise ValidationError(f'Could not find available KeyVault name for: {keyvault_name}')
        kv_name = f'{keyvault_name}{counter}' if len(keyvault_name) <= 23 else f"{keyvault_name[:23]}{counter}"
        counter = counter + 1
        logger.info(f'Checking availability of KeyVault name: {kv_name}')
        name_availability = vaults_client.check_name_availability(
            VaultCheckNameAvailabilityParameters(name=kv_name))

    return kv_name


def _check_storage_account_name_availability(cmd, storage_account_name):
    storage_name = storage_account_name
    storage_client = cf_storage(cli_ctx=cmd.cli_ctx).storage_accounts
    StorageAccountCheckNameAvailabilityParameters = cmd.get_models('StorageAccountCheckNameAvailabilityParameters',
                                                                   resource_type=ResourceType.MGMT_STORAGE,
                                                                   operation_group='storage_accounts')

    logger.info(f'Checking availability of Storage Account name: {storage_name}')
    name_availability = storage_client.check_name_availability(
        StorageAccountCheckNameAvailabilityParameters(name=storage_name))

    counter = 0
    while name_availability.name_available is False:
        logger.info(f'Storage Account name not available: {storage_name}')
        if counter > 9:
            raise ValidationError(f'Could not find available Storage Account name for: {storage_account_name}')
        storage_name = f'{storage_account_name}{counter}' if len(storage_account_name) <= 23 \
            else f"{storage_account_name[:23]}{counter}"
        counter = counter + 1
        logger.info(f'Checking availability of Storage Account name: {storage_name}')
        name_availability = storage_client.check_name_availability(
            StorageAccountCheckNameAvailabilityParameters(name=storage_name))

    return storage_name


def _get_sandbox_keyvault_name(cmd, name_prefix):
    # ex. contoso-images-kv
    # req: (3-24) Alphanumerics and hyphens. Start with letter. End with letter or digit.
    #             Can't contain consecutive hyphens. Globally unique.
    kv_name = ''

    # only allow alphanumeric and hyphens
    for char in name_prefix.strip().strip('-'):
        if char.isalnum() or char == '-':
            kv_name = kv_name + char

    # ensure first char is alpha
    while not kv_name[0].isalpha():
        kv_name = kv_name[1:]

    # ensure no consecutive hyphens
    while '--' in kv_name:
        kv_name = kv_name.replace('--', '-')

    kv_name_len = len(kv_name)
    kv_name = f'{kv_name}-kv' if kv_name_len <= 21 \
        else f'{kv_name}kv' if kv_name_len <= 22 \
        else kv_name if kv_name_len <= 24 \
        else kv_name[:24]

    # ensure last char is alpha or num
    while not kv_name[-1].isalnum():
        kv_name = kv_name[:-1]

    return _check_keyvault_name_availability(cmd, kv_name)


def _get_sandbox_storage_name(cmd, name_prefix):
    # ex. contosoimagesstorage
    # req: (3-24) Lowercase letters and numbers only. Globally unique.
    storage_name = ''

    # only allow lowercase alphanumeric
    for char in name_prefix.strip().lower():
        if char.isalnum():
            storage_name = storage_name + char

    storage_name_len = len(storage_name)
    storage_name = f'{storage_name}storage' if storage_name_len <= 17 \
        else f'{storage_name}store' if storage_name_len <= 19 \
        else f'{storage_name}stor' if storage_name_len <= 20 \
        else storage_name if storage_name_len <= 24 \
        else storage_name[:24]

    return _check_storage_account_name_availability(cmd, storage_name)


def _get_sandbox_vnet_name(cmd, name_prefix):  # pylint: disable=unused-argument
    # ex. contoso-images-vnet
    # req: (2-64) Alphanumerics, underscores, periods, and hyphens. Start with alphanumeric.
    #             End alphanumeric or underscore. Resource Group unique.
    vnet_name = ''

    # only allow alphanumeric, underscore, period, and hyphen
    for char in name_prefix.strip():
        if char.isalnum() or char == '_' or char == '.' or char == '-':
            vnet_name = vnet_name + char

    # ensure first char is alphanumeric
    while not vnet_name[0].isalpha():
        vnet_name = vnet_name[1:]

    vnet_name_len = len(vnet_name)

    vnet_name = f'{vnet_name}-vnet' if vnet_name_len <= 59 \
        else vnet_name if vnet_name_len <= 64 \
        else vnet_name[:64]

    # ensure last char is alphanumeric or underscore
    while not vnet_name[-1].isalnum() and vnet_name[-1] != '_':
        vnet_name = vnet_name[:-1]

    return vnet_name


def _get_sandbox_identity_name(cmd, name_prefix):  # pylint: disable=unused-argument
    # ex. contoso-images-id
    # req: (3-128) Alphanumerics, underscores, and hyphens. Start with alphanumeric. Resource Group unique.
    identity_name = ''

    # only allow alphanumeric, underscore, and hyphen
    for char in name_prefix.strip():
        if char.isalnum() or char == '_' or char == '-':
            identity_name = identity_name + char

    # ensure first char is alphanumeric
    while not identity_name[0].isalpha():
        identity_name = identity_name[1:]

    identity_name_len = len(identity_name)

    identity_name = f'{identity_name}-id' if identity_name_len <= 125 \
        else identity_name if identity_name_len <= 128 \
        else identity_name[:128]

    return identity_name


def get_sandbox_resource_names(cmd, name_prefix):
    kv_name = _get_sandbox_keyvault_name(cmd, name_prefix)
    storage_name = _get_sandbox_storage_name(cmd, name_prefix)
    vnet_name = _get_sandbox_vnet_name(cmd, name_prefix)
    identity_name = _get_sandbox_identity_name(cmd, name_prefix)

    return {
        'keyvault': kv_name,
        'storage': storage_name,
        'vnet': vnet_name,
        'identity': identity_name
    }
