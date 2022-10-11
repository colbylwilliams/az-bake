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

from ._arm import (create_image_definition, create_subnet,
                   deploy_arm_template_at_resource_group,
                   ensure_gallery_permissions, get_arm_output, get_gallery,
                   get_image_definition, get_image_version,
                   get_resource_group_tags, image_version_exists,
                   tag_resource_group)
from ._client_factory import cf_msi, cf_network
from ._constants import (AZ_BAKE_BUILD_IMAGE_NAME, AZ_BAKE_IMAGE_BUILDER,
                         AZ_BAKE_IMAGE_BUILDER_VERSION, AZ_BAKE_REPO_VOLUME,
                         AZ_BAKE_STORAGE_VOLUME, BAKE_PLACEHOLDER,
                         BAKE_PROPERTIES, IMAGE_PROPERTIES, KEY_ALLOWED,
                         KEY_REQUIRED, PKR_AUTO_VARS_FILE, PKR_BUILD_FILE,
                         PKR_PACKAGES_CONFIG_FILE, PKR_VARS_FILE, TAG_PREFIX,
                         tag_key)
from ._github import (get_github_release, get_release_templates,
                      get_template_url)
from ._packer import (check_packer_install, copy_packer_files,
                      inject_choco_provisioners, save_packer_vars_file)
from ._utils import get_yaml_file_contents, get_yaml_file_path

logger = get_logger(__name__)


def bake_test(cmd):
    from ._github import get_github_release
    foo = get_github_release(prerelease=True)
    return foo['tag_name']


def bake_builder_build(cmd, in_builder=False, repo=None, storage=None, sandbox=None, gallery=None, image=None, suffix=None):

    if in_builder:
        from azure.cli.command_modules.profile.custom import login
        # from azure.cli.core._profile import Profile
        from azure.cli.core.auth.identity import (AZURE_CLIENT_ID,
                                                  AZURE_CLIENT_SECRET,
                                                  AZURE_TENANT_ID)

        # profile = Profile(cli_ctx=cmd.cli_ctx)
        az_client_id = os.environ.get(AZURE_CLIENT_ID, None)
        az_client_secret = os.environ.get(AZURE_CLIENT_SECRET, None)
        az_tenant_id = os.environ.get(AZURE_TENANT_ID, None)

        if az_client_id and az_client_secret and az_tenant_id:
            logger.info(f'Found credentials for Azure Service Principal')
            logger.info(f'Logging in with Service Principal')
            login(cmd=cmd, service_principal=True, allow_no_subscriptions=True,
                  username=az_client_id, password=az_client_secret, tenant=az_tenant_id)
        else:
            logger.info(f'No credentials for Azure Service Principal')
            logger.info(f'Logging in to Azure with managed identity')
            login(cmd=cmd, allow_no_subscriptions=True, identity=True)
    else:
        logger.warning('Not in builder. Skipping login.')

    # logger.warning(json.dumps(sandbox, indent=4))
    # logger.warning(json.dumps(gallery, indent=4))
    # logger.warning(image)

    # copy build.pkr.hcl and variable.pkr.hcl to the image directory
    copy_packer_files(image['dir'])

    from ._utils import get_choco_package_config, get_install_choco_dict

    choco_install = get_install_choco_dict(image)

    choco_config = get_choco_package_config(choco_install)
    # logger.warning(choco_config)

    # create the choco packages config file
    inject_choco_provisioners(image['dir'], choco_config)

    save_packer_vars_file(sandbox, gallery, image)

    gallery_res = get_gallery(cmd, gallery['resourceGroup'], gallery['name'])

    definition = get_image_definition(cmd, gallery['resourceGroup'], gallery['name'], image['name'])
    if not definition:
        logger.warning(f'Image definition {image["name"]} does not exist. Creating...')
        definition = create_image_definition(cmd, gallery['resourceGroup'], gallery['name'], image['name'], image['publisher'],
                                             image['offer'], image['sku'], gallery_res.location)
    elif image_version_exists(cmd, gallery['resourceGroup'], gallery['name'], image['name'], image['version']):
        raise CLIError('Image version already exists')

    logger.warning(f'Image version {image["version"]} does not exist.')

    pass


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


def bake_sandbox_validate(cmd, sandbox_resource_group_name, gallery_resource_id=None, sandbox=None, gallery=None):
    if gallery_resource_id and 'identityId' in sandbox and sandbox['identityId']:
        identity_id = sandbox['identityId']
        if not is_valid_resource_id(identity_id):
            raise CLIError(f'Invalid sandbox identityId: {identity_id}\n Must be a valid resource id')
        logger.warning('Validating gallery permissions')
        ensure_gallery_permissions(cmd, gallery_resource_id, sandbox['identityId'])
    return True


# sandbox, gallery, and images come from validator
def bake_repo(cmd, repository_path, is_ci=False, image_names=None, sandbox=None, gallery=None, images=None):
    from azure.cli.command_modules.resource._bicep import \
        ensure_bicep_installation
    ensure_bicep_installation()

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
        from ._repos import get_repo
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

    from ._utils import get_choco_package_config

    choco = [
        {
            'id': 'googlechrome'
        },
        {
            'id': 'firefox',
        }
    ]

    choco_xml = get_choco_package_config(choco)
    logger.warning(choco_xml)

    image_dir = image['dir']
    image_name = image['name']
    image_file = image['file']
    # copy build.pkr.hcl and variable.pkr.hcl to the image directory
    copy_packer_files(image_dir)

    # create the choco packages config file
    inject_choco_provisioners(image_dir, choco_xml)

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
