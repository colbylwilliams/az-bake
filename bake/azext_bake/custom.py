# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------
# pylint: disable=line-too-long, logging-fstring-interpolation, too-many-locals, too-many-statements, unused-argument

import json
import os

from typing import Sequence

import yaml

from azure.cli.core.azclierror import CLIError, InvalidArgumentValueError, MutuallyExclusiveArgumentError
from azure.cli.core.extension.operations import show_extension, update_extension
from packaging.version import parse as parse_version

from ._arm import (create_image_definition, create_resource_group, deploy_arm_template_at_resource_group,
                   ensure_gallery_permissions, get_arm_output, get_gallery, get_image_definition,
                   get_resource_group_by_name, image_version_exists)
from ._client_factory import cf_container, cf_container_groups
from ._constants import (BAKE_YAML_SCHEMA, DEVOPS_PIPELINE_CONTENT, DEVOPS_PIPELINE_FILE, DEVOPS_PROVIDER_NAME,
                         GITHUB_PROVIDER_NAME, GITHUB_WORKFLOW_CONTENT, GITHUB_WORKFLOW_DIR, GITHUB_WORKFLOW_FILE,
                         IMAGE_DEFAULT_BASE_WINDOWS, IMAGE_YAML_SCHEMA, IN_BUILDER)
from ._data import Gallery, Image, Sandbox, get_dict
from ._github import get_github_latest_release_version, get_github_release, get_release_templates, get_template_url
from ._packer import (copy_packer_files, inject_choco_install_provisioners,
                      inject_choco_machine_provisioners, inject_choco_user_script_provisioners,
                      inject_choco_user_provisioners, inject_choco_machine_log_provisioners,
                      inject_powershell_provisioner, inject_choco_user_consent_provisioners,
                      inject_update_provisioner, packer_execute, save_packer_vars_file)
from ._repos import Repo
from ._sandbox import get_builder_subnet_id, get_sandbox_resource_names
from ._utils import (copy_to_builder_output_dir, get_install_choco_packages,
                     get_install_powershell_scripts, get_logger, get_templates_path)

logger = get_logger(__name__)


# def bake_tests(cmd):


# ----------------
# bake sandbox
# ----------------

def bake_sandbox_create(cmd, location, name_prefix, sandbox_resource_group_name=None, gallery_resource_id=None,
                        tags=None, principal_id=None, vnet_address_prefix='10.0.0.0/24',
                        default_subnet_name='default', default_subnet_address_prefix='10.0.0.0/25',
                        builders_subnet_name='builders', builders_subnet_address_prefix='10.0.0.128/25',
                        version=None, prerelease=False, local_templates=False, templates_url=None, template_file=None):

    # TODO: check if principal_id is provided, if not create and use msi

    sb_names = get_sandbox_resource_names(cmd, name_prefix)

    hook = cmd.cli_ctx.get_progress_controller()
    hook.begin()

    hook.add(message=f'Getting resource group {sandbox_resource_group_name}')
    rg, _ = get_resource_group_by_name(cmd.cli_ctx, sandbox_resource_group_name)
    if rg is None:
        if location is None:
            raise CLIError(f"--location/-l is required if resource group '{sandbox_resource_group_name}' does not exist")
        hook.add(message=f"Resource group '{sandbox_resource_group_name}' not found")
        hook.add(message=f"Creating resource group '{sandbox_resource_group_name}'")
        rg, _ = create_resource_group(cmd.cli_ctx, sandbox_resource_group_name, location)

    location = rg.location

    if local_templates:
        logger.warning('Using local template')
        template_file = str(get_templates_path('sandbox') / 'sandbox.bicep')
        template_uri = None
    elif template_file:
        logger.warning(f'Deploying user specified template: {template_file}')
        template_uri = None
    else:
        hook.add(message='Getting templates from GitHub')
        version, templates = get_release_templates(version=version, prerelease=prerelease, templates_url=templates_url)
        logger.info(f'Deploying{" prerelease" if prerelease else ""} version: {version}')

        hook.add(message='Getting sandbox template')
        template_uri = get_template_url(templates, 'sandbox', 'sandbox.json')

    logger.info('Getting deployment params')
    params = [
        f'location={location}',
        f'keyVaultName={sb_names["keyvault"]}',
        f'storageName={sb_names["storage"]}',
        f'vnetName={sb_names["vnet"]}',
        f'identityName={sb_names["identity"]}',
        f'vnetAddressPrefixes={json.dumps([vnet_address_prefix])}',
        f'defaultSubnetName={default_subnet_name}',
        f'defaultSubnetAddressPrefix={default_subnet_address_prefix}',
        f'builderSubnetName={builders_subnet_name}',
        f'builderSubnetAddressPrefix={builders_subnet_address_prefix}',
        f'tags={json.dumps(tags)}',
    ]

    if principal_id:
        params.append(f'ciPrincipalId={principal_id}')

    if gallery_resource_id:
        params.append(f'galleryIds={json.dumps([gallery_resource_id])}')

    hook.add(message='Creating sandbox environment')
    logger.info('Deploying sandbox...')
    _, _ = deploy_arm_template_at_resource_group(cmd, sandbox_resource_group_name,
                                                 template_file=template_file, template_uri=template_uri,
                                                 parameters=[params])
    logger.info('Finished deploying sandbox')
    print('Successfully deployed sandbox environment')
    # print(f'You can configure it as your default sandbox using `az configure --defaults bake-sandbox={sandbox_resource_group_name}`')

    hook.end(message=' ')


def bake_sandbox_validate(cmd, sandbox_resource_group_name: str, gallery_resource_id: str = None,
                          sandbox: Sandbox = None, gallery: Gallery = None):
    logger.info('Validating gallery permissions')
    ensure_gallery_permissions(cmd, gallery_resource_id, sandbox.identity_id)
    print('Sandbox is valid')


# ----------------
# bake repo
# ----------------

def bake_repo_build(cmd, repository_path, image_names: Sequence[str] = None, sandbox: Sandbox = None,
                    gallery: Gallery = None, images: Sequence[Image] = None, repository_url: str = None,
                    repository_token: str = None, repository_revision: str = None, repo: Repo = None):

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

    params = [
        f'subnetId={get_builder_subnet_id(sandbox)}',
        f'storageAccount={sandbox.storage_account}',
        f'identityId={sandbox.identity_id}',
        f'repository={repo.clone_url}'
    ]

    if repo.revision:
        params.append(f'revision={repo.revision}')

    for image in images:
        logger.info(f'Getting deployment params for {image.name} builder')

        image_params = params.copy()
        image_params.append(f'image={image.name}')
        image_params.append(f'version={image.version}')

        hook.add(message=f'Deploying {image.name} builder')
        logger.info(f'Deploying {image.name} builder...')
        deployment, outputs = deploy_arm_template_at_resource_group(cmd, sandbox.resource_group, template_file=template_file,
                                                                    template_uri=template_uri, parameters=[image_params])
        logs = get_arm_output(outputs, 'logs')
        bake_logs = get_arm_output(outputs, 'bake')
        portal = get_arm_output(outputs, 'portal')

        logger.warning(f'Finished deploying builder for {image.name} but packer is still running.')
        logger.warning('You can check the progress of the packer build:')
        logger.warning(f'  - Azure CLI: {logs}')
        logger.warning(f'  - Az Bake CLI: {bake_logs}')
        logger.warning(f'  - Azure Portal: {portal}')
        logger.warning('')

        if repo and repo.provider == GITHUB_PROVIDER_NAME:
            github_step_summary = os.environ.get('GITHUB_STEP_SUMMARY', None)
            if github_step_summary:
                summary = [
                    f'## Building {image.name}',
                    'You can check the progress of the packer build:',
                    f'- Azure CLI: `{logs}`', f'- Az Bake CLI: `{bake_logs}`', f'- Azure Portal: {portal}', ''
                ]
                with open(github_step_summary, 'a+', encoding='utf-8') as f:
                    f.write('\n'.join(summary))

        deployments.append(deployment)

    hook.end(message=' ')


def bake_repo_validate(cmd, repository_path, sandbox: Sandbox = None, gallery: Gallery = None, images: Sequence[Image] = None):
    logger.info('Validating repository')


def bake_repo_setup(cmd, sandbox_resource_group_name: str, gallery_resource_id: str, repository_path='./',
                    repository_provider: str = None, sandbox: Sandbox = None, gallery: Gallery = None):
    logger.info('Setting up repository')

    # logger.warning(repository_provider)
    _bake_yaml_export(sandbox=sandbox, gallery=gallery, outdir=repository_path)

    if repository_provider == GITHUB_PROVIDER_NAME:
        workflows_dir = repository_path / GITHUB_WORKFLOW_DIR

        if not workflows_dir.exists():
            workflows_dir.mkdir(parents=True, exist_ok=True)

        with open(workflows_dir / GITHUB_WORKFLOW_FILE, 'w', encoding='utf-8') as f:
            f.write(GITHUB_WORKFLOW_CONTENT)

    elif repository_provider == DEVOPS_PROVIDER_NAME:

        with open(repository_path / DEVOPS_PIPELINE_FILE, 'w', encoding='utf-8') as f:
            f.write(DEVOPS_PIPELINE_CONTENT)
    else:
        raise InvalidArgumentValueError(f'--repo-provider/--provider must be one of {GITHUB_PROVIDER_NAME} '
                                        f'or {DEVOPS_PROVIDER_NAME}')


# ----------------
# bake image
# ----------------


def bake_image_create(cmd, image_name, repository_path='./'):
    logger.info('Creating image.yml file')

    image = Image({
        'name': image_name,
        'version': '0.0.1',
        'description': f'A description for {image_name}',
        'publisher': 'MyCompany',
        'offer': 'DevBox',
        'sku': image_name.lower(),
        'os': 'Windows',
        'replicaLocations': ['eastus', 'westus'],
        'update': True,
        'base': IMAGE_DEFAULT_BASE_WINDOWS,
        'install': {
            'choco': {
                'packages': ['git', 'googlechrome', ]
            }
        }
    })

    image_obj = get_dict(image)

    yaml_str = f'{IMAGE_YAML_SCHEMA}\n' + yaml.safe_dump(image_obj, default_flow_style=False, sort_keys=False)

    image_dir = repository_path / 'images' / image_name
    if image_dir.exists():
        raise CLIError(f'Image directory already exists: {image_dir}')

    image_dir.mkdir(parents=True, exist_ok=True)

    image_file = image_dir / 'image.yml'

    with open(image_file, 'w', encoding='utf-8') as f:
        f.write(yaml_str)

    logger.warning(f'Created image.yml file: {image_file}')
    logger.warning('The image was generated with default values. You should review the file and make any necessary changes.')


def bake_image_logs(cmd, sandbox_resource_group_name, image_name, sandbox: Sandbox = None):
    container_client = cf_container(cmd.cli_ctx)
    container_group_client = cf_container_groups(cmd.cli_ctx)
    container_group = container_group_client.get(sandbox.resource_group, image_name)

    # we only have one container in the group
    container_name = container_group.containers[0].name
    log = container_client.list_logs(sandbox.resource_group, image_name, container_name)
    print(log.content)


def bake_image_bump(cmd, repository_path='./', image_names: Sequence[str] = None, images: Sequence[Image] = None,
                    major: bool = False, minor: bool = False):
    logger.info('Bumping image version')

    if major and minor:
        raise MutuallyExclusiveArgumentError('Only use one of --major | --minor')

    for image in images:
        version = image.version
        version_old = parse_version(version)

        if len(version_old.release) != 3:
            raise CLIError(f'Version must be in the format major.minor.patch (found: {version})')

        n_major = version_old.major + 1 if major else version_old.major
        n_minor = 0 if major else version_old.minor + 1 if minor else version_old.minor
        n_patch = 0 if major or minor else version_old.micro + 1

        version_new = parse_version(f'{n_major}.{n_minor}.{n_patch}')

        print(f'Bumping version for {image.name} {version_old.public} -> {version_new.public}')

        with open(image.file, 'r', encoding='utf-8') as f:
            image_yaml = f.read()

        if f'version: {version_old.public}' not in image_yaml:
            raise CLIError(f"Version string 'version {version_old.public}' not found in {image.file}")

        image_yaml = image_yaml.replace(f'version: {version_old.public}', f'version: {version_new.public}')

        with open(image.file, 'w', encoding='utf-8') as f:
            f.write(image_yaml)

        # print(f'Bumping version for {image.name} from {image.version} to {bump_version(image.version)}')


# ----------------
# bake yaml
# ----------------

def bake_yaml_export(cmd, sandbox_resource_group_name, gallery_resource_id,
                     sandbox: Sandbox = None, gallery: Gallery = None, images: Sequence[Image] = None,
                     outfile='./bake.yml', outdir=None, stdout=False):
    _bake_yaml_export(sandbox=sandbox, gallery=gallery, images=images, outfile=outfile, outdir=outdir, stdout=stdout)


# ----------------
# bake version
# bake upgrade
# ----------------

def bake_version(cmd):
    ext = show_extension('bake')
    current_version = 'v' + ext['version']
    is_dev = 'extensionType' in ext and ext['extensionType'] == 'dev'
    logger.info(f'Current version: {current_version}')
    current_version_parsed = parse_version(current_version)
    print(f'az bake version: {current_version}{" (dev)" if is_dev else ""}')

    latest_version = get_github_latest_release_version()
    logger.info(f'Latest version: {latest_version}')
    latest_version_parsed = parse_version(latest_version)

    if current_version_parsed < latest_version_parsed:
        logger.warning(f'There is a new version of az bake {latest_version}. Please update using: az bake upgrade')


def bake_upgrade(cmd, version=None, prerelease=False):
    ext = show_extension('bake')
    current_version = 'v' + ext['version']
    logger.info(f'Current version: {current_version}')
    current_version_parsed = parse_version(current_version)

    release = get_github_release(version=version, prerelease=prerelease)

    new_version = release['tag_name']
    logger.info(f'Latest{" prerelease" if prerelease else ""} version: {new_version}')
    new_version_parsed = parse_version(new_version)

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
        logger.warning('Skipping upgrade of dev extension.')
        return

    update_extension(cmd, extension_name='bake', index_url=index_url)


# ----------------
# bake _builder
# ----------------

def bake_builder_build(cmd, sandbox: Sandbox = None, gallery: Gallery = None, image: Image = None, suffix=None):

    if IN_BUILDER:
        from azure.cli.command_modules.profile.custom import login
        from azure.cli.core.auth.identity import AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID

        az_client_id = os.environ.get(AZURE_CLIENT_ID, None)
        az_client_secret = os.environ.get(AZURE_CLIENT_SECRET, None)
        az_tenant_id = os.environ.get(AZURE_TENANT_ID, None)

        if az_client_id and az_client_secret and az_tenant_id:
            logger.info('Found credentials for Azure Service Principal')
            logger.info('Logging in with Service Principal')
            login(cmd=cmd, service_principal=True, allow_no_subscriptions=True,
                  username=az_client_id, password=az_client_secret, tenant=az_tenant_id)
        else:
            logger.info('No credentials for Azure Service Principal')
            logger.info('Logging in to Azure with managed identity')
            login(cmd=cmd, allow_no_subscriptions=True, identity=True)
    else:
        logger.info('Not in builder. Skipping login.')

    gallery_res = get_gallery(cmd, gallery.resource_group, gallery.name)
    if not gallery_res:
        raise CLIError(f'Could not find gallery {gallery.name} in resource group {gallery.resource_group}')

    definition = get_image_definition(cmd, gallery.resource_group, gallery.name, image.name)
    if not definition:
        logger.info(f'Image definition {image.name} does not exist. Creating...')
        definition = create_image_definition(cmd, gallery.resource_group, gallery.name, image.name,
                                             image.publisher, image.offer, image.sku, gallery_res.location)
    elif image_version_exists(cmd, gallery.resource_group, gallery.name, image.name, image.version):
        raise CLIError('Image version already exists')

    logger.info(f'Image version {image.version} does not exist.')

    if copy_packer_files(image.dir):
        if image.update:
            inject_update_provisioner(image.dir)

        powershell_scripts = get_install_powershell_scripts(image)
        if powershell_scripts:
            inject_powershell_provisioner(image.dir, powershell_scripts)

        choco_packages = get_install_choco_packages(image)

        # install choco packages if packages
        if choco_packages:
            inject_choco_install_provisioners(image.dir)

            machine_choco_packages = [package for package in choco_packages if not package.user]
            if machine_choco_packages:
                inject_choco_machine_provisioners(image.dir, machine_choco_packages)
                inject_choco_machine_log_provisioners(image.dir)

            user_choco_packages = [package for package in choco_packages if package.user]
            if user_choco_packages:
                inject_choco_user_script_provisioners(image.dir)
                inject_choco_user_consent_provisioners(image.dir)
                inject_choco_user_provisioners(image.dir, user_choco_packages)

        # winget_config = get_install_winget(image)
        # if winget_config:
        #     inject_winget_provisioners(image.dir, winget_config)

    save_packer_vars_file(sandbox, gallery, image)

    copy_to_builder_output_dir(image.dir)

    success = packer_execute(image) if IN_BUILDER else 0

    if success == 0:
        logger.info('Packer build succeeded')
    else:
        raise CLIError('Packer build failed')

    return success


# ----------------
# _private
# ----------------

def _bake_yaml_export(sandbox: Sandbox = None, gallery: Gallery = None, images: Sequence[Image] = None,
                      outfile=None, outdir=None, stdout=False):
    logger.info('Exporting bake.yaml file')

    bake_obj = {'version': 1.0, 'sandbox': get_dict(sandbox), 'gallery': get_dict(gallery)}

    if images:
        bake_obj['images'] = [get_dict(image) for image in images]

    yaml_str = f'{BAKE_YAML_SCHEMA}\n' + yaml.safe_dump(bake_obj, default_flow_style=False, sort_keys=False)

    if stdout:
        print(yaml_str)
    elif outfile or outdir:
        with open(outfile if outfile else outdir / 'bake.yml', 'w', encoding='utf-8') as f:
            f.write(yaml_str)
