# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------
# pylint: disable=logging-fstring-interpolation

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import yaml
from azure.cli.core.azclierror import (FileOperationError,
                                       InvalidArgumentValueError,
                                       MutuallyExclusiveArgumentError,
                                       RequiredArgumentMissingError,
                                       ValidationError)
from azure.cli.core.commands.client_factory import get_subscription_id
from azure.cli.core.commands.parameters import (
    get_resources_in_resource_group, get_resources_in_subscription)
from azure.cli.core.profiles import ResourceType
from azure.mgmt.core.tools import (is_valid_resource_id, parse_resource_id,
                                   resource_id)
# from azure.cli.core.util import is_guid
from knack.log import get_logger
# from knack.prompting import prompt_y_n
from knack.util import CLIError

from ._client_factory import cf_msi, cf_network
from ._constants import (BAKE_PLACEHOLDER, PKR_AUTO_VARS_FILE, PKR_BUILD_FILE,
                         PKR_PACKAGES_CONFIG_FILE, PKR_VARS_FILE, TAG_PREFIX,
                         tag_key)
from ._deploy_utils import (create_subnet,
                            deploy_arm_template_at_resource_group,
                            get_arm_output, get_resource_group_tags,
                            tag_resource_group)
from ._gallery import (create_image_definition, ensure_gallery_permissions,
                       get_gallery, get_image_definition, get_image_version,
                       image_version_exists)
from ._github_utils import (get_github_release, get_release_templates,
                            get_template_url)
from ._packer import check_packer_install
from ._utils import get_yaml_file_contents, get_yaml_file_path

logger = get_logger(__name__)


def bake_test(cmd):
    from ._github_utils import get_github_release
    foo = get_github_release(prerelease=True)
    return foo['tag_name']


def bake_sandbox_create(cmd, location, sandbox_resource_group_name, name_prefix,
                        tags=None, principal_id=None, vnet_address_prefix='10.0.0.0/24',
                        default_subnet_name='default', default_subnet_address_prefix='10.0.0.0/25',
                        builders_subnet_name='builders', builders_subnet_address_prefix='10.0.0.128/25',
                        version=None, prerelease=False, templates_url=None, template_file=None):

    # TODO: check if principal_id is provided, if not create and use msi

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
    # params.append(f'builderPrincipalId={principal_id}')
    params.append('vnetAddressPrefixes={}'.format(json.dumps([vnet_address_prefix])))
    params.append(f'defaultSubnetName={default_subnet_name}')
    params.append(f'defaultSubnetAddressPrefix={default_subnet_address_prefix}')
    params.append(f'builderSubnetName={builders_subnet_name}')
    params.append(f'builderSubnetAddressPrefix={builders_subnet_address_prefix}')
    params.append(f'tags={json.dumps(tags)}')

    hook.add(message='Creating sandbox environment')
    deployment, _ = deploy_arm_template_at_resource_group(cmd, sandbox_resource_group_name,
                                                          template_file=template_file, template_uri=template_uri,
                                                          parameters=[params])
    hook.end(message=' ')
    return deployment


def bake_sandbox_validate(cmd, sandbox_resource_group_name, gallery_resource_id=None):

    tags = get_resource_group_tags(cmd, sandbox_resource_group_name)

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
        resources = get_resources_in_resource_group(cmd.cli_ctx, sandbox_resource_group_name)

    # check for identity
    if not identity_id:
        identity = next((r for r in resources if r.type == 'Microsoft.ManagedIdentity/userAssignedIdentities'), None)
        if not identity:
            raise CLIError('No identity found in sandbox resource group')
        identity_id = identity.id

    if not is_valid_resource_id(identity_id):
        raise CLIError('Invalid identity id. Must be a resource id')

    if gallery_resource_id:
        identity_id = ensure_gallery_permissions(cmd, gallery_resource_id, identity_id)

    # check for keyvault
    if not keyvault_name:
        keyvault = next((r for r in resources if r.type == 'Microsoft.KeyVault/vaults'), None)
        if not keyvault:
            raise CLIError('Could not find keyvault in sandbox resource group')
        keyvault_name = keyvault.name

    # check for storage
    if not storage_account:
        storage = next((r for r in resources if r.type == 'Microsoft.Storage/storageAccounts'), None)
        if not storage:
            raise CLIError('Could not find storage in sandbox resource group')
        storage_account = storage.name

    # check for vnet
    if not vnet_name:
        vnet = next((r for r in resources if r.type == 'Microsoft.Network/virtualNetworks'), None)
        if not vnet:
            raise CLIError('Could not find vnet in sandbox resource group')
        vnet_name = vnet.name

    if not default_subnet or not builder_subnet:
        net_client = cf_network(cmd.cli_ctx).virtual_networks
        vnet = net_client.get(sandbox_resource_group_name, vnet_name)

        # check for builders subnet
        delegated_subnets = [s for s in vnet.subnets if s.delegations and any([d for d in s.delegations if d.service_name == 'Microsoft.ContainerInstance/containerGroups'])]
        if not delegated_subnets:
            raise CLIError('Could not find builders subnet (delegated to ACI) in vnet')
        if len(delegated_subnets) > 1:
            raise CLIError('Found more than one subnet delegated to ACI in vnet. Cant determine which subnet to use for builders.')
        builder_subnet = delegated_subnets[0]

        # check for default subnet
        other_subnets = [s for s in vnet.subnets if s.id != builder_subnet.id]
        if not other_subnets:
            raise CLIError('Could not find a default subnet in vnet')
        if len(other_subnets) > 1:
            raise CLIError('Found more than one subnet (not delegated to ACI) in vnet. Cant determine which subnet to use for default.')
        default_subnet = other_subnets[0]

        default_subnet = default_subnet.name
        builder_subnet = builder_subnet.name

    bake_yaml = {
        'version': 1.0
    }

    bake_yaml['sandbox'] = {
        'resourceGroup': sandbox_resource_group_name,
        'subscription': sub,
        'virtualNetwork': vnet_name,
        'virtualNetworkResourceGroup': sandbox_resource_group_name,
        'defaultSubnet': default_subnet,
        'builderSubnet': builder_subnet,
        'keyVault': keyvault_name,
        'storageAcccount': storage_account,
        'identityId': identity_id
    }

    if gallery_resource_id:
        gallery_id = parse_resource_id(gallery_resource_id)
        bake_yaml['gallery'] = {
            'name': gallery_id['name'],
            'resourceGroup': gallery_id['resource_group'],
            'subscription': gallery_id['subscription'],
        }

    # bake_yaml['images'] = {
    #     'publisher': 'Contoso',
    #     'offer': 'DevBox',
    #     'replicaLocations': ['eastus', 'westus'],
    # }

    bake_file = os.path.abspath('/Users/colbylwilliams/GitHub/colbylwilliams/az-bake/.local/bake_test3.yaml')

    with open(bake_file, 'w+') as f:
        yaml.safe_dump(bake_yaml, f, default_flow_style=False, sort_keys=False)

    # tags = {
    #     tag_key('builder:storageAccount'): storage.name,
    #     tag_key('builder:subnetId'): builder_subnet.id,
    #     # tag_key('cli:version'): 'v0.0.2',
    #     tag_key('image:buildResourceGroup'): sandbox_resource_group_name,
    #     tag_key('image:keyVault'): keyvault.name,
    #     tag_key('image:subscription'): sub,
    #     tag_key('image:virtualNetwork'): vnet.name,
    #     tag_key('image:virtualNetworkResourceGroup'): sandbox_resource_group_name,
    #     tag_key('image:virtualNetworkSubnet'): default_subnet.name,
    #     # tag_key('sandbox:baseName'): 'colbysbtemp3',
    #     # tag_key('sandbox:builderPrincipalId'): 'ae2d3344-c4a5-41bd-85c7-644bc3bea8a4',
    #     # tag_key('sandbox:version'): 'v0.0.4'
    # }

    return tags


# sandbox, gallery, and images come from validator
def bake_repo(cmd, repository_path, is_ci=False, image_names=None, sandbox=None, gallery=None, images=None):

    hook = cmd.cli_ctx.get_progress_controller()
    hook.begin()

    version = None
    template_file = None
    prerelease = False
    templates_url = None

    repository_url = None
    repository_token = None
    repository_revision = None
    suffix = None

    suffix = suffix if suffix else datetime.now(timezone.utc).strftime('%Y%m%d%H%M')

    if template_file:
        logger.warning('Deploying local version of template')
        template_uri = None
    else:
        hook.add(message='Getting templates from GitHub')
        version, _, builder, _ = get_release_templates(
            version=version, prerelease=prerelease, templates_url=templates_url)

        logger.warning('Deploying%s version: %s', ' prerelease' if prerelease else '', version)

        hook.add(message='Getting builder template')
        template_uri = get_template_url(builder, 'builder.json')

    deployments = []

    params = []

    if is_ci:
        logger.warning('Running in CI mode')
        from ._ci import get_repo
        repo = get_repo()

        for prop in ['provider', 'url', 'ref', 'sha']:
            if prop not in repo:
                raise CLIError(f'Repo is missing {prop} property')
            if not repo[prop]:
                raise CLIError(f'Repo {prop} property is empty')

        params['repository'] = repo['url']
        params['revision'] = repo['sha']

    else:
        from ._repos import parse_repo_url

        repo = parse_repo_url(repository_url)

        if repository_token:
            repo['url'] = repo['url'].replace('https://', f'https://{repository_token}@')

        params['repository'] = repo['url']
        if repository_revision:
            params['revision'] = repository_revision

    subnet_id = resource_id(subscription=sandbox['subscription'], resource_group=sandbox['virtualNetworkResourceGroup'],
                            namespace='Microsoft.Network', type='virtualNetworks', name=sandbox['virtualNetwork'],
                            child_type_1='subnets', child_name_1=sandbox['builderSubnet'])

    params['subnetId'] = subnet_id
    params['storageAccount'] = sandbox['storageAccount']
    params['identityId'] = sandbox['identityId']

    for image in images:
        params['image'] = image['name']
        params['version'] = image['version']

        hook.add(message=f'Deploying builder for ')
        deployment, outputs = deploy_arm_template_at_resource_group(cmd, sandbox['resourceGroup'],
                                                                    template_file=template_file, template_uri=template_uri,
                                                                    parameters=[params])
        deployments.append(deployment)

    hook.end(message=' ')
    return deployments


def bake_repo_validate(cmd, repository_path, sandbox=None, gallery=None, images=None):
    for image in images:
        logger.warning(f'image: {image}')
        logger.warning('')
    logger.warning(f'gallery: {gallery}')
    logger.warning('')
    logger.warning(f'sandbox: {sandbox}')
    logger.warning('')

    return 'bake_repo_validate'


def bake_repo_test(cmd, repository_path, images=None):
    pass


def bake_image(cmd, image_path, sandbox_resource_group_name=None, bake_yaml=None, gallery_resource_id=None,
               gallery=None, sandbox=None, image=None):
    check_packer_install(raise_error=True)
    # from azure.core.exceptions import ResourceNotFoundError

    # if gallery_resource_id:
    #     gallery_parts = parse_resource_id(gallery_resource_id)
    #     gallery = get_gallery(cmd, gallery_parts['resource_group'], gallery_parts['name'])

    logger.warning(f'bake_yaml: {bake_yaml}')
    logger.warning(f'gallery: {gallery}')
    logger.warning(f'sandbox: {sandbox}')
    logger.warning(f'image: {image}')

    # if bake_yaml:
    #     bake_obj = get_yaml_file_contents(bake_yaml)

    # allow user to specify the image.yaml file or parent folder
    # image_path = Path(image_path).resolve()
    # if not image_path.exists():
    #     raise ValidationError(f'Could not find image file or directory at {image_path}')
    # if image_path.is_file():
    #     image_dir = image_path.parent
    #     image_name = image_path.parent.name
    #     image_file = image_path
    # if image_path.is_dir():
    #     image_dir = image_path
    #     image_file = get_yaml_file_path(image_dir, 'image', required=True)
    #     image_name = image_path.name

    import tempfile

    from ._utils import get_choco_config

    templates_dir = Path(__file__).resolve().parent / 'templates'

    choco = [
        {
            'id': 'googlechrome'
        },
        {
            'id': 'firefox',
        }
    ]

    choco_xml = get_choco_config(choco)
    logger.warning(choco_xml)

    image_dir = image['dir']
    image_name = image['name']
    image_file = image['file']
    # copy build.pkr.hcl and variable.pkr.hcl to the image directory
    shutil.copy2(templates_dir / PKR_BUILD_FILE, image_dir)
    shutil.copy2(templates_dir / PKR_VARS_FILE, image_dir)

    # create the choco packages config file
    with open(image_dir / PKR_PACKAGES_CONFIG_FILE, 'w') as f:
        f.write(choco_xml)

    choco_install = f'''
  # Injected by az bake
  provisioner "file" {{
    source = "${{path.root}}/{PKR_PACKAGES_CONFIG_FILE}"
    destination = "C:/Windows/Temp/{PKR_PACKAGES_CONFIG_FILE}"
  }}

  # Injected by az bake
  provisioner "powershell" {{
    elevated_user     = build.User
    elevated_password = build.Password
    inline = [
      "choco install C:/Windows/Temp/{PKR_PACKAGES_CONFIG_FILE} --yes --no-progress"
    ]
  }}
    '''

    # inject chocolatey install into build.pkr.hcl
    with open(image_dir / PKR_BUILD_FILE, 'r') as f:
        pkr_build = f.read()

    if BAKE_PLACEHOLDER not in pkr_build:
        raise ValidationError(f'Could not find {BAKE_PLACEHOLDER} in {PKR_BUILD_FILE}')

    pkr_build = pkr_build.replace(BAKE_PLACEHOLDER, choco_install)

    with open(image_dir / PKR_BUILD_FILE, 'w') as f:
        f.write(pkr_build)

    # shutil.copy2(image_file, image_dir)

    logger.warning(f'Image file {image_file}')
    logger.warning(f'Image name {image_name}')
    logger.warning(f'Image dir {image_dir}')

    # if not gallery:
    #     raise CLIError('Could not find gallery')

    # gallery_image_name = 'FooBarBox'
    # gallery_image_version_name = '1.0.0'
    # publisher = 'Contoso'
    # offer = 'DevBox'
    # sku = 'win11-foobar'

    # definition = get_image_definition(cmd, resource_group_name, gallery_name, gallery_image_name) \
    #     or create_image_definition(cmd, resource_group_name, gallery_name, gallery_image_name, publisher, offer, sku, gallery.location)

    # if image_version_exists(cmd, resource_group_name, gallery_name, gallery_image_name, gallery_image_version_name):
    #     raise CLIError('Image version already exists')

    # image_version = get_image_version(cmd, resource_group_name, gallery_name, gallery_image_name, gallery_image_version_name)

    return True


def bake_image_test(cmd, resource_group_name, gallery_name):
    from azure.core.exceptions import ResourceNotFoundError

    gallery = get_gallery(cmd, resource_group_name, gallery_name)

    if not gallery:
        raise CLIError('Could not find gallery')

    gallery_image_name = 'FooBarBox'
    gallery_image_version_name = '1.0.0'
    publisher = 'Contoso'
    offer = 'DevBox'
    sku = 'win11-foobar'

    definition = get_image_definition(cmd, resource_group_name, gallery_name, gallery_image_name) \
        or create_image_definition(cmd, resource_group_name, gallery_name, gallery_image_name, publisher, offer, sku, gallery.location)

    if image_version_exists(cmd, resource_group_name, gallery_name, gallery_image_name, gallery_image_version_name):
        raise CLIError('Image version already exists')

    # image_version = get_image_version(cmd, resource_group_name, gallery_name, gallery_image_name, gallery_image_version_name)

    return definition

    # try:
    #     definition = client.gallery_images.get(resource_group_name, gallery.name, 'VSCodeBox')
    #     if not definition:
    #         raise CLIError('Could not find definition')
    # except ResourceNotFoundError:
    #     GalleryImage, GalleryImageIdentifier, RecommendedMachineConfiguration, ResourceRange, Disallowed, ImagePurchasePlan, GalleryImageFeature = cmd.get_models(
    #         'GalleryImage', 'GalleryImageIdentifier', 'RecommendedMachineConfiguration', 'ResourceRange', 'Disallowed', 'ImagePurchasePlan', 'GalleryImageFeature',
    #         resource_type=ResourceType.MGMT_COMPUTE)
    #     purchase_plan = None
    #     # if any([plan_name, plan_publisher, plan_product]):
    #     #     purchase_plan = ImagePurchasePlan(name=plan_name, publisher=plan_publisher, product=plan_product)
    #     feature_list = [
    #         GalleryImageFeature(name='SecurityType', value='TrustedLaunch')
    #     ]

    #     # image = GalleryImage(identifier=GalleryImageIdentifier(publisher=publisher, offer=offer, sku=sku),
    #     #                      os_type='Windows', os_state='Generalized', end_of_life_date=None,
    #     #                     recommended=None, disallowed=Disallowed(disk_types=disallowed_disk_types),
    #     #                     purchase_plan=purchase_plan, location=location, eula=eula, tags=(tags or {}),
    #     #                     hyper_v_generation='V2', features=feature_list, architecture=architecture)

    #     return 'TODO: Create definition'

    # try:
    #     version = client.gallery_image_versions.get(resource_group_name, gallery.name, definition.name, '1.0.1')
    #     if not version:
    #         raise CLIError('Could not find version')
    # except ResourceNotFoundError:
    #     return 'TODO: Create version'

    # return version


def bake_upgrade(cmd, version=None, prerelease=False):
    from azure.cli.core.extension.operations import update_extension
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
