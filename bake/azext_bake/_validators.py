# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------
# pylint: disable=unused-argument,

import ipaddress
import os
from datetime import datetime, timezone
from pathlib import Path
from re import match

from azure.cli.core.azclierror import (FileOperationError,
                                       InvalidArgumentValueError,
                                       MutuallyExclusiveArgumentError,
                                       RequiredArgumentMissingError,
                                       ValidationError)
from azure.cli.core.commands.validators import validate_tags
from azure.cli.core.extension import get_extension
from azure.mgmt.core.tools import (is_valid_resource_id, parse_resource_id,
                                   resource_id)
from knack.log import get_logger

from ._completers import get_default_location_from_sandbox_resource_group
from ._constants import (AZ_BAKE_BUILD_IMAGE_NAME, AZ_BAKE_IMAGE_BUILDER,
                         AZ_BAKE_IMAGE_BUILDER_VERSION, AZ_BAKE_REPO_VOLUME,
                         AZ_BAKE_STORAGE_VOLUME, BAKE_PROPERTIES,
                         GALLERY_PROPERTIES, IMAGE_PROPERTIES, KEY_ALLOWED,
                         KEY_REQUIRED, SANDBOX_PROPERTIES, tag_key)
from ._github import (get_github_latest_release_version,
                      github_release_version_exists)
from ._packer import check_packer_install
from ._sandbox import get_sandbox_from_group
from ._utils import get_yaml_file_contents, get_yaml_file_path

logger = get_logger(__name__)


def process_bake_image_namespace(cmd, ns):
    common = None
    if ns.bake_yaml:
        if ns.sandbox_resource_group_name or ns.gallery_resource_id:
            raise MutuallyExclusiveArgumentError('usage error: --bake-yaml can not be used with --sandbox or --gallery')
        bakeobj = bake_yaml_validator(cmd, ns)
        common = bakeobj['images']
    elif not ns.sandbox_resource_group_name or not ns.gallery_resource_id:
        raise RequiredArgumentMissingError('usage error: --sandbox and --gallery OR --bake-yaml is required')
    else:
        sandbox_resource_group_name_validator(cmd, ns)
        gallery_resource_id_validator(cmd, ns)

    image_path_validator(cmd, ns)
    image_yaml_validator(cmd, ns, common=common)


def process_bake_repo_namespace(cmd, ns):
    repository_path_validator(cmd, ns)
    repository_images_validator(cmd, ns)
    bake_obj = bake_yaml_validator(cmd, ns)
    for i, image in enumerate(ns.images):
        ns.images[i] = image_yaml_validator(cmd, ns, image=image, common=bake_obj['images'])


def process_bake_repo_validate_namespace(cmd, ns):
    repository_path_validator(cmd, ns)
    repository_images_validator(cmd, ns)
    bake_obj = bake_yaml_validator(cmd, ns)
    for i, image in enumerate(ns.images):
        ns.images[i] = image_yaml_validator(cmd, ns, image=image, common=bake_obj['images'])


def builder_validator(cmd, ns):
    check_packer_install(raise_error=True)

    in_builder = os.environ.get(AZ_BAKE_IMAGE_BUILDER)
    in_builder = True if in_builder else False
    ns.in_builder = in_builder

    builder_version = os.environ.get('{AZ_BAKE_IMAGE_BUILDER_VERSION}', 'unknown') if in_builder else 'local'

    logger.info(f'{AZ_BAKE_IMAGE_BUILDER}: {in_builder}')
    logger.info(f'{AZ_BAKE_IMAGE_BUILDER_VERSION}: {builder_version}')

    if not in_builder:
        logger.warning('WARNING: Running outside of the builder container. This should only be done during testing.')

    # if not in_builder:
    #     raise CLIError('Not in builder')

    repo = Path(AZ_BAKE_REPO_VOLUME) if in_builder else Path(__file__).resolve().parent.parent.parent
    storage = Path(AZ_BAKE_STORAGE_VOLUME) if in_builder else repo / '.local' / 'storage'

    _validate_dir_path(repo, 'repo')
    _validate_dir_path(storage, 'storage')

    ns.repo = repo
    ns.storage = storage

    # check for required environment variables
    for env in [AZ_BAKE_BUILD_IMAGE_NAME]:
        if not os.environ.get(env, False):
            raise ValidationError(f'Missing environment variable: {env}')

    image_name = os.environ[AZ_BAKE_BUILD_IMAGE_NAME]
    image_path = repo / 'images' / image_name

    _validate_dir_path(image_path, image_name)

    logger.info(f'Image name: {image_name}')
    logger.info(f'Image path: {image_path}')

    if not ns.suffix:
        ns.suffix = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')

    logger.info(f'Build suffix: {ns.suffix}')

    bake_yaml = get_yaml_file_path(repo, 'bake', required=True)

    bake_obj = bake_yaml_content_validator(cmd, ns, bake_yaml)

    image_dir = image_path
    image_file = get_yaml_file_path(image_dir, 'image', required=True)
    image_name = image_path.name
    ns.image = {
        'name': image_name,
        'dir': image_dir,
        'file': image_file,
    }

    image_yaml_validator(cmd, ns, common=bake_obj['images'])


def repository_images_validator(cmd, ns):
    if not ns.repository_path:
        raise RequiredArgumentMissingError('--repository-path/-r is required')

    images_path = _validate_dir_path(ns.repository_path/'images', name='images')

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
            raise InvalidArgumentValueError(f'--image/-i {bad_names} are not a valid images')

    ns.images = []

    # for each image, validate the image.yaml file exists and get the path
    for image_dir in image_dirs:
        if all_images or image_dir.name in images:
            ns.images.append({
                'name': image_dir.name,
                'dir': image_dir,
                'file': get_yaml_file_path(image_dir, 'image', required=True)
            })


def repository_path_validator(cmd, ns):
    if not ns.repository_path:
        raise RequiredArgumentMissingError('--repository-path/-r is required')

    repo_path = _validate_dir_path(ns.repository_path, name='repository')
    ns.repository_path = repo_path


def image_names_validator(cmd, ns):
    if ns.image_names:
        if not isinstance(ns.image_names, list):
            raise InvalidArgumentValueError('--image/-i must be a list of strings')


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


def bake_yaml_validator(cmd, ns):

    if hasattr(ns, 'repository_path') and ns.repository_path:
        logger.warning('repository_path')
        # should have already run the repository_path_validator
        path = get_yaml_file_path(ns.repository_path, 'bake', required=True)
    elif hasattr(ns, 'bake_yaml') and ns.bake_yaml:
        bake_yaml = Path(ns.bake_yaml).resolve()
        bake_yaml = get_yaml_file_path(bake_yaml.parent, 'bake', required=True)
        ns.bake_yaml = bake_yaml
        path = bake_yaml
    else:
        logger.warning('no repository_path or bake_yaml')
        raise RequiredArgumentMissingError('usage error: --repository-path or --bake-yaml is required.')

    return bake_yaml_content_validator(cmd, ns, path)


def bake_yaml_content_validator(cmd, ns, path):
    bake_obj = get_yaml_file_contents(path)
    bake_obj['name'] = path.name
    bake_obj['dir'] = path.parent
    bake_obj['file'] = path

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


def sandbox_resource_group_name_validator(cmd, ns):
    has_bake_yaml = hasattr(ns, 'bake_yaml') and ns.bake_yaml is not None
    if ns.sandbox_resource_group_name and has_bake_yaml:
        raise MutuallyExclusiveArgumentError('usage error: --bake-yaml and --sandbox are mutually exclusive')

    sandbox = get_sandbox_from_group(cmd, ns.sandbox_resource_group_name)

    _validate_object(ns.sandbox_resource_group_name, sandbox, SANDBOX_PROPERTIES)

    if hasattr(ns, 'sandbox'):
        ns.sandbox = sandbox


def gallery_resource_id_validator(cmd, ns):
    if ns.gallery_resource_id:
        if not is_valid_resource_id(ns.gallery_resource_id):
            raise InvalidArgumentValueError('usage error: --gallery/-r is not a valid resource id')

        if hasattr(ns, 'gallery'):
            gallery_id = parse_resource_id(ns.gallery_resource_id)
            ns.gallery = {
                'name': gallery_id['name'],
                'resourceGroup': gallery_id['resource_group'],
                'subscription': gallery_id['subscription'],
            }


def bake_source_version_validator(cmd, ns):
    if ns.version:
        if ns.prerelease:
            raise MutuallyExclusiveArgumentError(
                'Only use one of --version/-v | --pre',
                recommendation='Remove all --version/-v, and --pre to use the latest stable release,'
                ' or only specify --pre to use the latest pre-release')

        _validate_version(cmd, ns)


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
            _validate_version(cmd, ns)

        elif ns.templates_url:
            if not _is_valid_url(ns.templates_url):
                raise InvalidArgumentValueError(
                    '--templates-url should be a valid url to a templates.json file')

        else:
            ns.version = ns.version or get_github_latest_release_version(prerelease=ns.prerelease)
            ns.templates_url = f'https://github.com/colbylwilliams/az-bake/releases/download/{ns.version}/templates.json'


def _validate_object(path, obj, properties, parent_key=None):

    key_prefix = f'{parent_key}.' if parent_key else ''

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


def _validate_version(cmd, ns):
    ns.version = ns.version.lower()
    if ns.version[:1].isdigit():
        ns.version = 'v' + ns.version

    if not _is_valid_version(ns.version):
        raise InvalidArgumentValueError(
            '--version/-v should be in format v0.0.0 do not include -pre suffix')

    if not github_release_version_exists(version=ns.version):
        raise InvalidArgumentValueError(f'--version/-v {ns.version} does not exist')


def _is_valid_version(version):
    return match(r'^v[0-9]+\.[0-9]+\.[0-9]+$', version) is not None


def _is_valid_url(url):
    return match(
        r'^http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\), ]|(?:%[0-9a-fA-F][0-9a-fA-F]))+$', url) is not None


def _none_or_empty(val):
    return val in ('', '""', "''") or val is None


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
