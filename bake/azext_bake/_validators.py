# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

import ipaddress
import os
from pathlib import Path
from re import match

import yaml
from azure.cli.core.azclierror import (FileOperationError,
                                       InvalidArgumentValueError,
                                       MutuallyExclusiveArgumentError,
                                       RequiredArgumentMissingError,
                                       ValidationError)
from azure.cli.core.commands.client_factory import get_subscription_id
from azure.cli.core.commands.parameters import (
    get_resources_in_resource_group, get_resources_in_subscription)
from azure.cli.core.commands.validators import validate_tags
from azure.cli.core.extension import get_extension
from azure.mgmt.core.tools import (is_valid_resource_id, parse_resource_id,
                                   resource_id)
from knack.log import get_logger

from ._client_factory import cf_msi, cf_network
from ._completers import get_default_location_from_sandbox_resource_group
from ._constants import (BAKE_PROPERTIES, IMAGE_PROPERTIES, KEY_ALLOWED,
                         KEY_REQUIRED, tag_key)
from ._deploy_utils import (create_subnet,
                            deploy_arm_template_at_resource_group,
                            get_arm_output, get_resource_group_tags,
                            tag_resource_group)
from ._github_utils import (get_github_latest_release_version,
                            github_release_version_exists)
from ._utils import get_yaml_file_contents, get_yaml_file_path

logger = get_logger(__name__)

# pylint: disable=unused-argument,


def process_bake_image_namespace(cmd, ns):
    logger.warning('1/3 Validating bake image repository')
    validate_bake(cmd, ns)
    logger.warning('2/3 Validating bake image')
    bake_obj = bake_yaml_validator(cmd, ns)
    logger.warning('3/3 Validating image')
    image_path_validator(cmd, ns)
    image_yaml_validator(cmd, ns, common=bake_obj['images'])


def process_bake_repo_namespace(cmd, ns):
    repository_path_validator(cmd, ns)
    bake_obj = bake_yaml_validator(cmd, ns)
    for i, image in enumerate(ns.images):
        ns.images[i] = image_yaml_validator(cmd, ns, image=image, common=bake_obj['images'])


def process_bake_repo_validate_namespace(cmd, ns):
    repository_path_validator(cmd, ns)
    bake_obj = bake_yaml_validator(cmd, ns)
    for i, image in enumerate(ns.images):
        ns.images[i] = image_yaml_validator(cmd, ns, image=image, common=bake_obj['images'])


def prefix_validator(cmd, ns):
    if not ns.prefix:
        raise InvalidArgumentValueError('--prefix|-p must be a valid string')


def bake_source_version_validator(cmd, ns):
    if ns.version:
        if ns.prerelease:
            raise MutuallyExclusiveArgumentError(
                'Only use one of --version/-v | --pre',
                recommendation='Remove all --version/-v, and --pre to use the latest stable release,'
                ' or only specify --pre to use the latest pre-release')

        ns.version = ns.version.lower()
        if ns.version[:1].isdigit():
            ns.version = 'v' + ns.version

        if not _is_valid_version(ns.version):
            raise InvalidArgumentValueError(
                '--version/-v should be in format v0.0.0 do not include -pre suffix')

        if not github_release_version_exists(version=ns.version):
            raise InvalidArgumentValueError(f'--version/-v {ns.version} does not exist')


def repository_path_validator(cmd, ns):
    if not ns.repository_path:
        raise RequiredArgumentMissingError('--repository-path/-r is required')

    repo_path = _validate_dir_path(ns.repository_path, name='repository')

    ns.repository_path = repo_path

    images_path = _validate_dir_path(repo_path/'images', name='images')

    image_dirs = []
    image_names = []

    images = getattr(ns, 'images_names', None)

    all_images = not images or not isinstance(images, list) or len(images) == 0

    # walk the images directory and find all the child directories
    for dirpath, dirnames, files in os.walk(images_path):
        # os.walk includes the root directory (i.e. repo/images) so we need to skip it
        if not images_path.samefile(dirpath) and Path(dirpath).parent.samefile(images_path):
            image_dirs.append(Path(dirpath))
            image_names.append(Path(dirpath).name)

    # if specific images were specified, validate they exist
    if not all_images:
        bad_names = [i for i in images if i not in image_names]
        if bad_names:
            raise InvalidArgumentValueError(f'--image/-i {bad_names} is not a valid image name')

    ns.images = []

    # for each image, validate the image.yaml file exists and get the path
    for image_dir in image_dirs:
        if all_images or image_dir.name in images:
            ns.images.append({
                'name': image_dir.name,
                'dir': image_dir,
                'file': get_yaml_file_path(image_dir, 'image', required=True)
            })


def templates_version_validator(cmd, ns):
    if ns.template_file:
        if ns.version or ns.prerelease or ns.templates_url:
            raise MutuallyExclusiveArgumentError(
                '--template-file cannont be used with --templates-url | --version/-v | --pre',
                recommendation='Remove all --templates-url, --version/-v, and --pre to use a local template file.')
    else:
        if sum(1 for ct in [ns.version, ns.prerelease, ns.templates_url] if ct) > 1:
            raise MutuallyExclusiveArgumentError(
                'Only use one of --templates-url | --version/-v | --pre',
                recommendation='Remove all --templates-url, --version/-v, and --pre to use the latest'
                'stable release, or only specify --pre to use the latest pre-release')

        if ns.version:
            ns.version = ns.version.lower()
            if ns.version[:1].isdigit():
                ns.version = 'v' + ns.version
            if not _is_valid_version(ns.version):
                raise InvalidArgumentValueError(
                    '--version/-v should be in format v0.0.0 do not include -pre suffix')

            if not github_release_version_exists(version=ns.version):
                raise InvalidArgumentValueError(f'--version/-v {ns.version} does not exist')

        elif ns.templates_url:
            if not _is_valid_url(ns.templates_url):
                raise InvalidArgumentValueError(
                    '--templates-url should be a valid url to a templates.json file')

        else:
            ns.version = ns.version or get_github_latest_release_version(prerelease=ns.prerelease)
            ns.templates_url = f'https://github.com/colbylwilliams/az-bake/releases/download/{ns.version}/templates.json'


def validate_sandbox_tags(cmd, ns):
    if ns.tags:
        validate_tags(ns)

    tags_dict = {} if ns.tags is None else ns.tags

    if ns.template_file:
        tags_dict.update({tag_key('sandbox-version'): 'local'})
    else:
        if ns.version:
            tags_dict.update({tag_key('sandbox-version'): ns.version})
        if ns.prerelease:
            tags_dict.update({tag_key('sandbox-prerelease'): ns.prerelease})

    ext = get_extension('bake')
    ext_version = ext.get_version()
    cur_version_str = f'v{ext_version}'

    tags_dict.update({tag_key('cli-version'): cur_version_str})

    ns.tags = tags_dict


def process_sandbox_create_namespace(cmd, ns):
    # validate_resource_prefix(cmd, ns)
    get_default_location_from_sandbox_resource_group(cmd, ns)
    templates_version_validator(cmd, ns)
    if _none_or_empty(ns.vnet_address_prefix):
        raise InvalidArgumentValueError(f'--vnet-address-prefix/--vnet-prefix must be a valid CIDR prefix')

    for subnet in ['default', 'builders']:
        validate_subnet(cmd, ns, subnet, [ns.vnet_address_prefix])

    validate_sandbox_tags(cmd, ns)
    # import json
    # logger.warning(json.dumps(ns.tags, indent=2))


def validate_subnet(cmd, ns, subnet, vnet_prefixes):
    subnet_name_option = f'--{subnet}-subnet-name/--{subnet}-subnet'
    subnet_prefix_option = f'--{subnet}-subnet-prefix/--{subnet}-prefix'

    subnet_name_arg = f'{subnet}_subnet_name'
    subnet_prefix_arg = f'{subnet}_subnet_address_prefix'

    subnet_name_val = getattr(ns, subnet_name_arg, None)
    if _none_or_empty(subnet_name_val):
        raise InvalidArgumentValueError(f'{subnet_name_option} must have a value')

    subnet_prefix_val = getattr(ns, subnet_prefix_arg, None)
    if _none_or_empty(subnet_prefix_val):
        raise InvalidArgumentValueError(f'{subnet_prefix_option} must be a valid CIDR prefix')

    # subnet_prefix_is_default = hasattr(getattr(ns, subnet_prefix_arg), 'is_default')

    vnet_networks = [ipaddress.ip_network(p) for p in vnet_prefixes]
    if not all(any(h in n for n in vnet_networks) for h in ipaddress.ip_network(subnet_prefix_val).hosts()):
        raise InvalidArgumentValueError(
            '{} {} is not within the vnet address space (prefixed: {})'.format(
                subnet_prefix_option, subnet_prefix_val, ', '.join(vnet_prefixes)))


def user_validator(cmd, ns):
    # Make sure these arguments are non-empty strings.
    # When they are accidentally provided as an empty string "", they won't take effect when filtering the role
    # assignments, causing all matched role assignments to be listed/deleted. For example,
    #   az role assignment delete --assignee ""
    # removes all role assignments under the subscription.
    if getattr(ns, 'user_id') == "":
        # Get option name, like user_id -> --user-id
        option_name = cmd.arguments['user_id'].type.settings['options_list'][0]
        raise RequiredArgumentMissingError(f'usage error: {option_name} can\'t be an empty string.')


def bake_yaml_validator(cmd, ns):

    if hasattr(ns, 'repository_path') and ns.repository_path:
        logger.warning('repository_path')
        path = get_yaml_file_path(ns.repository_path, 'bake', required=True)
    elif hasattr(ns, 'bake_yaml') and ns.bake_yaml:
        logger.warning('bake_yaml')
        bake_yaml = Path(ns.bake_yaml).resolve()
        bake_yaml = get_yaml_file_path(bake_yaml.parent, 'bake', required=True)
        ns.bake_yaml = bake_yaml
        path = bake_yaml
    else:
        logger.warning('no repository_path or bake_yaml')
        raise RequiredArgumentMissingError('usage error: --repository-path or --bake-yaml is required.')

    bake_obj = {
        'name': path.name,
        'dir': path.parent,
        'file': path,
    }

    bake_temp = get_yaml_file_contents(path)

    temp = bake_temp.copy()
    temp.update(bake_obj)
    bake_obj = temp

    _validate_object(bake_obj['file'], bake_obj, BAKE_PROPERTIES)

    for key in BAKE_PROPERTIES:
        if key not in [KEY_REQUIRED, KEY_ALLOWED]:
            _validate_object(bake_obj['file'], bake_obj[key], BAKE_PROPERTIES[key], parent_key=key)

    if hasattr(ns, 'bake_obj'):
        ns.bake_obj = bake_obj

    if hasattr(ns, 'sandbox'):
        ns.sandbox = bake_obj['sandbox']

    if hasattr(ns, 'gallery'):
        ns.gallery = bake_obj['gallery']

    return bake_obj


def image_path_validator(cmd, ns):
    # allow user to specify the image.yaml file or parent folder
    image_path = Path(ns.image_path).resolve()
    if not image_path.exists():
        raise ValidationError(f'Could not find image file or directory at {image_path}')
    if image_path.is_file():
        image_dir = image_path.parent
        image_name = image_path.parent.name
        image_file = image_path
    if image_path.is_dir():
        image_dir = image_path
        image_file = get_yaml_file_path(image_dir, 'image', required=True)
        image_name = image_path.name

    if hasattr(ns, 'image'):
        ns.image = {
            'name': image_name,
            'dir': image_dir,
            'file': image_file,
        }


def image_yaml_validator(cmd, ns, image=None, common=None):
    if image is None and hasattr(ns, 'image') and ns.image is not None:
        image = ns.image

    # TODO: may not need this
    img_temp = get_yaml_file_contents(image['file'])
    temp = img_temp.copy()
    temp.update(image)
    image = temp

    if common:
        img_common = common
        temp = img_common.copy()
        temp.update(image)
        image = temp.copy()

    # logger.warning(f'Validating image: {image["name"]}')
    _validate_object(image['file'], image, IMAGE_PROPERTIES)

    if hasattr(ns, 'image'):
        ns.image = image

    return image


def validate_bake(cmd, ns):
    has_bake_yaml = hasattr(ns, 'bake_yaml') and ns.bake_yaml is not None
    has_sandbox = hasattr(ns, 'sandbox_resource_group_name') and ns.sandbox_resource_group_name is not None

    if has_bake_yaml and has_sandbox:
        raise MutuallyExclusiveArgumentError(
            'usage error: --bake-yaml and --sandbox are mutually exclusive')

    if has_bake_yaml:
        bake_yaml_validator(cmd, ns)

    if has_sandbox:

        tags = get_resource_group_tags(cmd, ns.sandbox_resource_group_name)

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

        if not identity_id or not keyvault_name or not storage_account or not vnet_name:
            resources = get_resources_in_resource_group(cmd.cli_ctx, ns.sandbox_resource_group_name)

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
            vnet = net_client.get(ns.sandbox_resource_group_name, vnet_name)

            # check for builders subnet
            delegated_subnets = [s for s in vnet.subnets if s.delegations and any([d for d in s.delegations if d.service_name == 'Microsoft.ContainerInstance/containerGroups'])]
            if not delegated_subnets:
                raise ValidationError('Could not find builders subnet (delegated to ACI) in vnet')
            if len(delegated_subnets) > 1:
                raise ValidationError('Found more than one subnet delegated to ACI in vnet. Cant determine which subnet to use for builders.')
            builder_subnet = delegated_subnets[0]

            # check for default subnet
            other_subnets = [s for s in vnet.subnets if s.id != builder_subnet.id]
            if not other_subnets:
                raise ValidationError('Could not find a default subnet in vnet')
            if len(other_subnets) > 1:
                raise ValidationError('Found more than one subnet (not delegated to ACI) in vnet. Cant determine which subnet to use for default.')
            default_subnet = other_subnets[0]

            default_subnet = default_subnet.name
            builder_subnet = builder_subnet.name

        if hasattr(ns, 'sandbox'):
            ns.sandbox = {
                'resourceGroup': ns.sandbox_resource_group_name,
                'subscription': sub,
                'virtualNetwork': vnet_name,
                'virtualNetworkResourceGroup': ns.sandbox_resource_group_name,
                'defaultSubnet': default_subnet,
                'builderSubnet': builder_subnet,
                'keyVault': keyvault_name,
                'storageAcccount': storage_account,
                'identityId': identity_id
            }

    if hasattr(ns, 'gallery_resource_id') and ns.gallery_resource_id is not None:
        if hasattr(ns, 'gallery'):
            gallery_id = parse_resource_id(ns.gallery_resource_id)
            ns.gallery = {
                'name': gallery_id['name'],
                'resourceGroup': gallery_id['resource_group'],
                'subscription': gallery_id['subscription'],
            }

        # bake_yaml_validator(cmd, ns)


def _validate_object(path, obj, properties, parent_key=None):

    key_prefix = f'{parent_key}.' if parent_key else ''

    # if merge_obj:  # merge common properties into image properties
    #     temp = merge_obj.copy()
    #     temp.update(obj)
    #     obj = temp.copy()

    if KEY_REQUIRED in properties:
        for prop in properties[KEY_REQUIRED]:
            if prop not in obj:
                raise ValidationError(f'{path} is missing {KEY_REQUIRED} property: {key_prefix}{prop}')
            if not obj[prop]:
                raise ValidationError(f'{path} is missing a value for {KEY_REQUIRED} property: {key_prefix}{prop}')
    if KEY_ALLOWED in properties:
        for prop in obj:
            if prop not in properties[KEY_ALLOWED] and prop not in ['file', 'dir']:
                raise ValidationError(f'{path} contains an invalid property: {key_prefix}{prop}')

    return obj


def _validate_dir_path(path, name=None):
    dir_path = (path if isinstance(path, Path) else Path(path)).resolve()
    not_exists = f'Could not find {name} directory at {dir_path}' if name else f'{dir_path} is not a file or directory'
    if not dir_path.exists():
        raise ValidationError(not_exists)
    if not dir_path.is_dir():
        raise ValidationError(f'{dir_path} is not a directory')
    return dir_path


def _validate_file_path(path, name=None):
    file_path = (path if isinstance(path, Path) else Path(path)).resolve()
    not_exists = f'Could not find {name} file at {file_path}' if name else f'{file_path} is not a file or directory'
    if not file_path.exists():
        raise ValidationError(not_exists)
    if not file_path.is_file():
        raise ValidationError(f'{file_path} is not a file')
    return file_path


def _is_valid_url(url):
    return match(
        r'^http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\), ]|(?:%[0-9a-fA-F][0-9a-fA-F]))+$', url) is not None


def _is_valid_version(version):
    return match(r'^v[0-9]+\.[0-9]+\.[0-9]+$', version) is not None


def _none_or_empty(val):
    return val in ('', '""', "''") or val is None

    # def get_vnet(cmd, parts):
    #     client = network_client_factory(cmd.cli_ctx).virtual_networks
    #     rg, name = parts['resource_group'], parts['name']
    #     if not all([rg, name]):
    #         return None
    #     try:
    #         vnet = client.get(rg, name)
    #         return vnet
    #     except ResourceNotFoundError:
    #         return None

    # def get_subnet(cmd, parts):
    #     client = network_client_factory(cmd.cli_ctx).subnets
    #     rg, vnet, name = parts['resource_group'], parts['name'], parts['child_name_1']
    #     if not all([rg, vnet, name]):
    #         return None
    #     try:
    #         subnet = client.get(rg, vnet, name)
    #         return subnet
    #     except ResourceNotFoundError:
    #         return None
