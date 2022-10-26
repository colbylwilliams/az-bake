# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------
# pylint: disable=logging-fstring-interpolation

import json
import os

import yaml
from azure.cli.core.extension.operations import (show_extension,
                                                 update_extension)
from knack.util import CLIError
from packaging.version import parse

from ._arm import (create_image_definition,
                   deploy_arm_template_at_resource_group,
                   ensure_gallery_permissions, get_arm_output, get_gallery,
                   get_image_definition, image_version_exists)
from ._constants import IN_BUILDER
from ._github import (get_github_latest_release_version, get_github_release,
                      get_release_templates, get_template_url)
from ._packer import (check_packer_install, copy_packer_files,
                      inject_choco_provisioners, inject_winget_provisioners,
                      packer_execute, save_packer_vars_file)
from ._sandbox import get_builder_subnet_id
from ._utils import (get_choco_package_config, get_install_choco_dict,
                     get_install_winget, get_logger)

logger = get_logger(__name__)


# def bake_test(cmd):
#     from ._github import get_github_release
#     foo = get_github_release(prerelease=True)
#     return foo['tag_name']


def bake_builder_build(cmd, sandbox=None, gallery=None, image=None, suffix=None):
    if IN_BUILDER:
        from azure.cli.command_modules.profile.custom import login
        from azure.cli.core.auth.identity import (AZURE_CLIENT_ID,
                                                  AZURE_CLIENT_SECRET,
                                                  AZURE_TENANT_ID)

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
        logger.info('Not in builder. Skipping login.')

    gallery_res = get_gallery(cmd, gallery['resourceGroup'], gallery['name'])

    definition = get_image_definition(cmd, gallery['resourceGroup'], gallery['name'], image['name'])
    if not definition:
        logger.info(f'Image definition {image["name"]} does not exist. Creating...')
        definition = create_image_definition(cmd, gallery['resourceGroup'], gallery['name'], image['name'], image['publisher'],
                                             image['offer'], image['sku'], gallery_res.location)
    elif image_version_exists(cmd, gallery['resourceGroup'], gallery['name'], image['name'], image['version']):
        raise CLIError('Image version already exists')

    logger.info(f'Image version {image["version"]} does not exist.')

    if copy_packer_files(image['dir']):
        choco_install = get_install_choco_dict(image)
        if choco_install:
            choco_config = get_choco_package_config(choco_install)
            inject_choco_provisioners(image['dir'], choco_config)

        winget_config = get_install_winget(image)
        if winget_config:
            inject_winget_provisioners(image['dir'], winget_config)

    save_packer_vars_file(sandbox, gallery, image)

    success = packer_execute(image) if IN_BUILDER else 0

    if success == 0:
        logger.info('Packer build succeeded')
    else:
        raise CLIError('Packer build failed')

    return success

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
        version, templates = get_release_templates(version=version, prerelease=prerelease, templates_url=templates_url)
        logger.info(f'Deploying{" prerelease" if prerelease else ""} version: {version}')

        hook.add(message='Getting builder template')
        template_uri = get_template_url(templates, 'builder', 'builder.json')

    deployments = []

    params = []

    if repository_token:
        if repo['provider'] == 'github':
            logger.info('Adding GitHub token to repository url')
            params.append(f'repository={repository_url.replace("https://", f"https://gituser:{repository_token}@")}')
        elif repo['provider'] == 'azuredevops':
            logger.info('Adding DevOps token to repository url')
            params.append(f'repository={repository_url.replace("https://", f"https://azurereposuser:{repository_token}@")}')
        else:
            logger.info('Adding token to repository url')
            params.append(f'repository={repository_url.replace("https://", f"https://{repository_token}@")}')
    else:
        params.append(f'repository={repository_url}')

    if repository_revision:
        params.append(f'revision={repository_revision}')

    params.append(f'subnetId={get_builder_subnet_id(sandbox)}')
    params.append(f'storageAccount={sandbox["storageAccount"]}')
    params.append(f'identityId={sandbox["identityId"]}')

    for image in images:
        logger.info(f'Getting deployment params for {image["name"]} builder')
        image_params = params.copy()
        image_params.append(f'image={image["name"]}')
        image_params.append(f'version={image["version"]}')
        # logger.info(json.dumps(image_params, indent=2))
        hook.add(message=f'Deploying {image["name"]} builder')
        logger.info(f'Deploying {image["name"]} builder...')
        deployment, outputs = deploy_arm_template_at_resource_group(cmd, sandbox['resourceGroup'],
                                                                    template_file=template_file, template_uri=template_uri,
                                                                    parameters=[image_params])
        logs = get_arm_output(outputs, 'logs')
        portal = get_arm_output(outputs, 'portal')

        logger.warning(f'Finished deploying builder for {image["name"]} but packer is still running.')
        logger.warning(f'You can check the progress of the packer build:')
        logger.warning(f'  - Azure CLI: {logs}')
        logger.warning(f'  - Azure Portal: {portal}')
        logger.warning(f'')

        deployments.append(deployment)

    hook.end(message=' ')

    return


def bake_repo_validate(cmd, repository_path, sandbox=None, gallery=None, images=None):
    logger.info('Validating repository')
    return True
    # raise CLIError('Not implemented')


def bake_sandbox_create(cmd, location, sandbox_resource_group_name, name_prefix, gallery_resource_id=None,
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
        version, templates = get_release_templates(version=version, prerelease=prerelease, templates_url=templates_url)
        logger.info(f'Deploying{" prerelease" if prerelease else ""} version: {version}')

        hook.add(message='Getting sandbox template')
        template_uri = get_template_url(templates, 'sandbox', 'sandbox.json')

    logger.info(f'Getting deployment params')

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

    if gallery_resource_id:
        params.append('galleryIds={}'.format(json.dumps([gallery_resource_id])))

    hook.add(message='Creating sandbox environment')
    logger.info(f'Deploying sandbox...')
    deployment, outputs = deploy_arm_template_at_resource_group(cmd, sandbox_resource_group_name,
                                                                template_file=template_file, template_uri=template_uri,
                                                                parameters=[params])
    logger.info(f'Finished deploying sandbox')
    logger.warning(f'Successfully deployed sandbox environment')
    logger.warning(f'You can configure it as your default sandbox using `az configure --defaults bake-sandbox={sandbox_resource_group_name}`')

    hook.end(message=' ')

    return


def bake_sandbox_validate(cmd, sandbox_resource_group_name, gallery_resource_id=None, sandbox=None, gallery=None):
    logger.info('Validating gallery permissions')
    ensure_gallery_permissions(cmd, gallery_resource_id, sandbox['identityId'])
    print('Sandbox is valid')
    return


def bake_yaml_export(cmd, sandbox_resource_group_name, gallery_resource_id, sandbox=None, gallery=None, images=None,
                     outfile='./bake.yml', outdir=None, stdout=False):
    logger.info('Exporting bake.yaml file')

    bake_obj = {
        'version': 1.0,
        'sandbox': sandbox,
        'gallery': gallery
    }
    if images:
        bake_obj['images'] = images

    yaml_schema = '# yaml-language-server: $schema=https://github.com/colbylwilliams/az-bake/releases/latest/download/bake.schema.json\n'
    yaml_str = yaml_schema + yaml.safe_dump(bake_obj, default_flow_style=False, sort_keys=False)

    if stdout:
        print(yaml_str)
    elif outfile:
        with open(outfile, 'w') as f:
            f.write(yaml_str)
    elif outdir:
        with open(outdir / 'bake.yml', 'w') as f:
            f.write(yaml_str)

    return


def bake_yaml_validate(cmd):
    logger.info('Validating bake.yaml file')
    print('bake.yaml is valid')
    return


def bake_image(cmd, image_path, sandbox_resource_group_name=None, bake_yaml=None, gallery_resource_id=None,
               gallery=None, sandbox=None, image=None):
    check_packer_install(raise_error=True)
    raise CLIError('Not implemented')


def bake_version(cmd):
    ext = show_extension('bake')
    current_version = 'v' + ext['version']
    logger.info(f'Current version: {current_version}')
    current_version_parsed = parse(current_version)
    print(f'az bake version: {current_version}')

    latest_version = get_github_latest_release_version()
    logger.info(f'Latest version: {latest_version}')
    latest_version_parsed = parse(latest_version)

    if current_version_parsed < latest_version_parsed:
        logger.warning(f'There is a new version of az bake {latest_version}. Please update using: az bake upgrade')
    return


def bake_upgrade(cmd, version=None, prerelease=False):
    ext = show_extension('bake')
    current_version = 'v' + ext['version']
    logger.info(f'Current version: {current_version}')
    current_version_parsed = parse(current_version)

    release = get_github_release(version=version, prerelease=prerelease)

    new_version = release['tag_name']
    logger.info(f'Latest{" prerelease" if prerelease else ""} version: {new_version}')
    new_version_parsed = parse(new_version)

    is_dev = 'extensionType' in ext and ext['extensionType'] == 'dev'

    if not is_dev and new_version_parsed == current_version_parsed:
        print(f'Already on latest{" prerelease" if prerelease else ""} version: {new_version}')
        return

    if not is_dev and new_version_parsed < current_version_parsed:
        print(f'Current version is newer than latest{" prerelease" if prerelease else ""} version: {new_version}')
        return

    logger.info(f'Upgrading to latest{" prerelease" if prerelease else ""} version: {new_version}')
    index = next((a for a in release['assets'] if 'index.json' in a['browser_download_url']), None)

    index_url = index['browser_download_url'] if index else None
    if not index_url:
        raise CLIError(f'Could not find index.json asset on release {new_version}. '
                       'Specify a specific prerelease version with --version/-v or use latest prerelease with --pre')

    if is_dev:
        logger.warning(f'Skipping upgrade of dev extension.')
        return
    else:
        return update_extension(cmd, extension_name='bake', index_url=index_url)
