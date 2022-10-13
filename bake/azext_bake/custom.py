# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------
# pylint: disable=logging-fstring-interpolation

import json
import os

from knack.log import get_logger
from knack.util import CLIError

from ._arm import (create_image_definition,
                   deploy_arm_template_at_resource_group,
                   ensure_gallery_permissions, get_gallery,
                   get_image_definition, image_version_exists)
from ._github import (get_github_release, get_release_templates,
                      get_template_url)
from ._packer import (check_packer_install, copy_packer_files,
                      inject_choco_provisioners, packer_execute,
                      save_packer_vars_file)
from ._sandbox import get_builder_subnet_id
from ._utils import get_choco_package_config, get_install_choco_dict

logger = get_logger(__name__)


# def bake_test(cmd):
#     from ._github import get_github_release
#     foo = get_github_release(prerelease=True)
#     return foo['tag_name']


def bake_builder_build(cmd, in_builder=False, repo=None, storage=None, sandbox=None, gallery=None, image=None, suffix=None):

    logger.info('(info) hello world')
    logger.debug('(debug) hello world')
    logger.warning('(warning) hello world')

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

    gallery_res = get_gallery(cmd, gallery['resourceGroup'], gallery['name'])

    definition = get_image_definition(cmd, gallery['resourceGroup'], gallery['name'], image['name'])
    if not definition:
        logger.warning(f'Image definition {image["name"]} does not exist. Creating...')
        definition = create_image_definition(cmd, gallery['resourceGroup'], gallery['name'], image['name'], image['publisher'],
                                             image['offer'], image['sku'], gallery_res.location)
    elif image_version_exists(cmd, gallery['resourceGroup'], gallery['name'], image['name'], image['version']):
        raise CLIError('Image version already exists')

    logger.warning(f'Image version {image["version"]} does not exist.')

    logger.debug(f'Copying packer template files to image directory')
    copy_packer_files(image['dir'])

    logger.debug(f'Getting choco install dictionary from image.yaml')
    choco_install = get_install_choco_dict(image)

    logger.debug(f'Getting choco package config file from install dictionary')
    choco_config = get_choco_package_config(choco_install)

    logger.debug(f'Injecting choco provisioners into packer.json')
    inject_choco_provisioners(image['dir'], choco_config)

    logger.debug(f'Saving packer auto variables file to image directory')
    save_packer_vars_file(sandbox, gallery, image)

    logger.debug(f'Running packer init and packer build')
    return packer_execute(image)


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
    logger.warning('Validating gallery permissions')
    ensure_gallery_permissions(cmd, gallery_resource_id, sandbox['identityId'])
    return True


# sandbox, gallery, and images come from validator
def bake_repo(cmd, repository_path, is_ci=False, image_names=None, sandbox=None, gallery=None, images=None,
              repository_url=None, repository_token=None, repository_revision=None, repo=None):
    from azure.cli.command_modules.resource._bicep import \
        ensure_bicep_installation
    ensure_bicep_installation()

    hook = cmd.cli_ctx.get_progress_controller()
    hook.begin()

    version = None
    template_file = None
    prerelease = False
    templates_url = None

    if template_file:
        logger.warning('Deploying local version of template')
        template_uri = None
    else:
        hook.add(message='Getting templates from GitHub')
        version, _, builder, _ = get_release_templates(
            version=version, prerelease=prerelease, templates_url=templates_url)
        logger.warning(f'Deploying{" prerelease" if prerelease else ""} version: {version}')

        hook.add(message='Getting builder template')
        template_uri = get_template_url(builder, 'builder.json')

    deployments = []

    params = []

    if repository_token:
        if repo['provider'] == 'github':
            params.append(f'repository={repository_url.replace("https://", f"https://gituser:{repository_token}@")}')
        elif repo['provider'] == 'azuredevops':
            params.append(f'repository={repository_url.replace("https://", f"https://azurereposuser:{repository_token}@")}')
        else:
            params.append(f'repository={repository_url.replace("https://", f"https://{repository_token}@")}')
    else:
        params.append(f'repository={repository_url}')

    if repository_revision:
        params.append(f'revision={repository_revision}')

    params.append(f'subnetId={get_builder_subnet_id(sandbox)}')
    params.append(f'storageAccount={sandbox["storageAccount"]}')
    params.append(f'identityId={sandbox["identityId"]}')

    for image in images:
        image_params = params.copy()
        image_params.append(f'image={image["name"]}')
        image_params.append(f'version={image["version"]}')
        # logger.warning(json.dumps(image_params, indent=2))
        hook.add(message=f'Deploying builder for {image["name"]}')
        deployment, outputs = deploy_arm_template_at_resource_group(cmd, sandbox['resourceGroup'],
                                                                    template_file=template_file, template_uri=template_uri,
                                                                    parameters=[image_params])
        deployments.append(deployment)

    hook.end(message=' ')
    return deployments


def bake_repo_validate(cmd, repository_path, sandbox=None, gallery=None, images=None):
    raise CLIError('Not implemented')


def bake_image(cmd, image_path, sandbox_resource_group_name=None, bake_yaml=None, gallery_resource_id=None,
               gallery=None, sandbox=None, image=None):
    check_packer_install(raise_error=True)
    raise CLIError('Not implemented')


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
