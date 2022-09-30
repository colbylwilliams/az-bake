# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------
# pylint: disable=logging-fstring-interpolation

import json

# from azure.cli.core.util import is_guid
from knack.log import get_logger
# from knack.prompting import prompt_y_n
from knack.util import CLIError

from ._deploy_utils import (create_subnet,
                            deploy_arm_template_at_resource_group,
                            get_arm_output, get_resource_group_tags,
                            tag_resource_group)
# from ._client_factory import (get_graph_client)
from ._github_utils import get_release_templates, get_template_url

logger = get_logger(__name__)


def bake_test(cmd):
    from ._github_utils import get_github_release
    foo = get_github_release(prerelease=True)
    return foo['tag_name']


def bake_upgrade(cmd, version=None, prerelease=False):
    from azure.cli.core.extension.operations import update_extension

    from ._github_utils import get_github_release

    release = get_github_release(version=version, prerelease=prerelease)

    index = next((a for a in release['assets']
                  if 'index.json' in a['browser_download_url']), None)

    index_url = index['browser_download_url'] if index else None

    if not index_url:
        raise CLIError(
            f"Could not find index.json asset on release {release['tag_name']}. "
            'Specify a specific prerelease version with --version '
            'or use latest prerelease with --pre')

    update_extension(cmd, extension_name='bake', index_url=index_url)


def bake_sandbox_create(cmd, location, sandbox_resource_group_name, name_prefix,
                        tags=None, principal_id=None, vnet_address_prefix='10.0.0.0/24',
                        default_subnet_name='default', default_subnet_address_prefix='10.0.0.0/25',
                        builders_subnet_name='builders', builders_subnet_address_prefix='10.0.0.128/25',
                        version=None, prerelease=False, templates_url=None, template_file=None):

    # logger.warning(f'prerelease: {prerelease}')
    # logger.warning(f'version: {version}')
    # logger.warning(f'templates_url: {templates_url}')
    # logger.warning(f'tags: {tags}')
    # return []

    # TODO: check if principal_id is provided, if not, create a new one

    hook = cmd.cli_ctx.get_progress_controller()
    hook.begin()

    if template_file:
        logger.warning('Deploying local version of template')
        template_uri = None
    else:
        hook.add(message='Getting templates from GitHub')
        version, sandbox, _, _ = get_release_templates(
            version=version, prerelease=prerelease, templates_url=templates_url)

        logger.warning('Deploying%s version: %s', ' prerelease' if prerelease else '', version)

        hook.add(message='Getting sandbox template')
        template_uri = get_template_url(sandbox, 'sandbox.json')

    params = []
    params.append(f'location={location}')
    params.append(f'baseName={name_prefix}')
    params.append(f'builderPrincipalId={principal_id}')
    params.append('vnetAddressPrefixes={}'.format(json.dumps([vnet_address_prefix])))
    params.append(f'defaultSubnetName={default_subnet_name}')
    params.append(f'defaultSubnetAddressPrefix={default_subnet_address_prefix}')
    params.append(f'builderSubnetName={builders_subnet_name}')
    params.append(f'builderSubnetAddressPrefix={builders_subnet_address_prefix}')
    params.append(f'tags={json.dumps(tags)}')

    hook.add(message='Creating sandbox environment')
    deployment, outputs = deploy_arm_template_at_resource_group(cmd, sandbox_resource_group_name,
                                                                template_file=template_file, template_uri=template_uri,
                                                                parameters=[params])

    # build_resource_group = get_arm_output(outputs, 'buildResourceGroup')
    # key_vault = get_arm_output(outputs, 'keyVault')
    # virtual_network = get_arm_output(outputs, 'virtualNetwork')
    # virtual_network_subnet = get_arm_output(outputs, 'virtualNetworkSubnet')
    # virtual_network_resourceGroup = get_arm_output(outputs, 'virtualNetworkResourceGroup')
    # subscription = get_arm_output(outputs, 'subscription')
    # aci_storage_account = get_arm_output(outputs, 'aciStorageAccount')
    # aci_subnet_id = get_arm_output(outputs, 'aciSubnetId')

    hook.end(message=' ')
    # foo = {
    #     'buildResourceGroup': {
    #         'value': build_resource_group,
    #         'description': 'The value for the buildResourceGroup property in the images.yml and image.yml file.'
    #     },
    #     'keyVault': {
    #         'value': key_vault,
    #         'description': 'The value for the string property in the images.yml and image.yml file.'
    #     },
    #     'virtualNetwork': {
    #         'value': virtual_network,
    #         'description': 'The value for the virtualNetwork property in the images.yml and image.yml file.'
    #     },
    #     'virtualNetworkSubnet': {
    #         'value': virtual_network_subnet,
    #         'description': 'The value for the virtualNetworkSubnet property in the images.yml and image.yml file.'
    #     },
    #     'virtualNetworkResourceGroup': {
    #         'value': virtual_network_resourceGroup,
    #         'description': 'The value for the virtualNetworkResourceGroup property in the images.yml and image.yml file.'
    #     },
    #     'subscription': {
    #         'value': subscription,
    #         'description': 'The value for the subscription property in the images.yml and image.yml file.'
    #     },
    #     'aciStorageAccount': {
    #         'value': aci_storage_account,
    #         'description': 'The storage account name to pass as the value for the --storage-account argument when executing aci.py'
    #     },
    #     'aciSubnetId': {
    #         'value': aci_subnet_id,
    #         'description': 'The subnet id to pass as the value for the --subnet-id argument when executing aci.py'
    #     }
    # }

    return deployment


def bake_sandbox_validate(cmd, sandbox_resource_group_name):
    pass
