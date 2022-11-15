# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------
# pylint: disable=logging-fstring-interpolation

import json

from pathlib import Path
from xml.dom import minidom
from xml.etree.ElementTree import Element, tostring

import yaml

from azure.cli.core.azclierror import FileOperationError, ValidationError
from knack.log import get_logger as knack_get_logger

from ._constants import IN_BUILDER, OUTPUT_DIR, STORAGE_DIR


def get_logger(name):
    '''Get the logger for the extension'''
    _logger = knack_get_logger(name)

    if IN_BUILDER and STORAGE_DIR.is_dir():
        import logging
        log_file = OUTPUT_DIR / 'builder.txt'
        formatter = logging.Formatter('{asctime} [{name:^28}] {levelname:<8}: {message}',
                                      datefmt='%m/%d/%Y %I:%M:%S %p', style='{',)
        fh = logging.FileHandler(log_file)
        fh.setLevel(level=_logger.level)
        fh.setFormatter(formatter)
        _logger.addHandler(fh)

    return _logger


logger = get_logger(__name__)


def get_templates_path(folder=None):
    '''Get the path to the templates folder'''
    path = Path(__file__).resolve().parent / 'templates'
    return path / folder if folder else path


def get_yaml_file_path(dirpath, file, required=True):
    '''Get the path to a yaml or yml file in a directory'''
    dir_path = (dirpath if isinstance(dirpath, Path) else Path(dirpath)).resolve()

    if not dir_path.is_dir():
        if required:
            raise ValidationError(f'Directory for yaml/yml {file} not found at {dirpath}')
        return None

    yaml_path = dir_path / f'{file}.yaml'
    yml_path = dir_path / f'{file}.yml'

    yaml_isfile = yaml_path.is_file()
    yml_isfile = yml_path.is_file()

    if not yaml_isfile and not yml_isfile:
        if required:
            raise ValidationError(f'File {file}.yaml or {file}.yml not found in {dirpath}')
        return None

    if yaml_isfile and yml_isfile:
        raise ValidationError(f'Found both {file}.yaml and {file}.yml in {dirpath} of repository. '
                              f'Only one {file} yaml file allowed')

    file_path = yaml_path if yaml_path.is_file() else yml_path

    return file_path


def get_yaml_file_contents(path):
    '''Get the contents of a yaml file'''
    path = (path if isinstance(path, Path) else Path(path)).resolve()
    if not path.is_file():
        raise FileOperationError(f'Could not find yaml file at {path}')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            obj = yaml.safe_load(f)
    except OSError:  # FileNotFoundError introduced in Python 3
        raise FileOperationError(f'No such file or directory: {path}')  # pylint: disable=raise-missing-from
    except yaml.YAMLError as e:
        raise FileOperationError('Error while parsing yaml file:\n\n' + str(e))  # pylint: disable=raise-missing-from
    if obj is None:
        raise FileOperationError(f'Yaml file cannot be empty: {path}')
    return obj


def get_install_choco_dict(image):
    '''Get the dict for the install choco section supplemented by the index'''
    logger.info('Getting choco install dictionary from image.yaml')
    if 'install' not in image or 'choco' not in image['install']:
        return None

    if 'packages' not in image['install']['choco']:
        raise ValidationError('No packages found in install.choco in image.yaml')

    install_path = get_templates_path('install')
    choco_index_path = install_path / 'choco.json'
    choco_index = {}
    with open(choco_index_path, 'r', encoding='utf-8') as f:
        choco_index = json.load(f)

    choco = []

    choco_defaults = image['install']['choco']['defaults'] if 'defaults' in image['install']['choco'] else None

    for c in image['install']['choco']['packages']:
        logger.info(f'Getting choco config for {c} type {type(c)}')
        if isinstance(c, str):
            # if only the id was givin, check the index for the rest of the config
            choco_node = choco_index[c] if c in choco_index else {'id': c}
        elif isinstance(c, dict):
            # if the full config was given, use it
            choco_node = c
        else:
            raise ValidationError(f'Invalid choco config {c} in image {image["name"]}')

        # if defaults were given, add them to the config
        if choco_defaults:  # merge common properties into image properties
            temp = choco_defaults.copy()
            temp.update(choco_node)
            choco_node = temp.copy()

        choco.append(choco_node)

    return choco


def get_choco_package_config(packages, indent=2):
    '''Get the chocolatey package config file'''
    logger.info('Getting choco package config contents from install dict')
    elem = Element('packages')
    for package in packages:
        child = Element('package', package)
        # child.text = package
        elem.append(child)
    # prettify
    xml_string = tostring(elem).decode("utf-8")
    xml_string = minidom.parseString(xml_string)
    xml_string = xml_string.toprettyxml(indent=' ' * indent)

    return xml_string


def get_install_winget(image):
    '''Get the dict for the install winget section supplemented by the index'''
    logger.info('Getting wingit install dictionary from image.yaml')
    if 'install' not in image or 'winget' not in image['install']:
        return None

    if 'packages' not in image['install']['winget']:
        raise ValidationError('No packages found in install.winget in image.yaml')

    install_path = get_templates_path('install')
    winget_index_path = install_path / 'winget.json'
    winget_index = {}
    with open(winget_index_path, 'r', encoding='utf-8') as f:
        winget_index = json.load(f)

    winget = []

    winget_defaults = image['install']['winget']['defaults'] if 'defaults' in image['install']['winget'] else None

    for c in image['install']['winget']['packages']:
        logger.info(f'Getting winget config for {c} type {type(c)}')
        if isinstance(c, str):
            # if only the id was givin, check the index for the rest of the config
            winget_node = winget_index[c] if c in winget_index else {'ANY': c}
        elif isinstance(c, dict):
            # if the full config was given, use it
            winget_node = c
        else:
            raise ValidationError(f'Invalid winget config {c} in image {image["name"]}')

        # if defaults were given, add them to the config
        if winget_defaults:  # merge common properties into image properties
            temp = winget_defaults.copy()
            temp.update(winget_node)
            winget_node = temp.copy()

        winget.append(winget_node)

    return winget


def get_install_powershell_scripts(image):
    logger.info('Getting powershell scripts install dictionary from image.yaml')
    if 'install' not in image or 'scripts' not in image['install']:
        return None

    if 'powershell' not in image['install']['scripts']:
        raise ValidationError('Image install.scripts must include a powershell section')

    img_dir = image['dir'].resolve()

    scripts = []

    for script in image['install']['scripts']['powershell']:
        logger.info(f'Getting powershell script config for {script} type {type(script)}')
        if isinstance(script, str):
            # if only the path was givin add it to the list
            _validate_file_path(image['dir'] / script)
            script_path = str(img_dir / script).replace(str(img_dir), '${path.root}')
            scripts.append({'path': script_path, 'restart': False})
        elif isinstance(script, dict):
            # if the full object was given, use it
            _validate_file_path(image['dir'] / script['path'])
            script_path = str(img_dir / script['path']).replace(str(img_dir), '${path.root}')
            scripts.append({'path': script_path, 'restart': script['restart'] if 'restart' in script else False})
        else:
            raise ValidationError(f'Invalid powershell script config {script} in image {image["name"]}')

    return scripts


def _validate_file_path(path, name=None):
    file_path = (path if isinstance(path, Path) else Path(path)).resolve()
    not_exists = f'Could not find {name} file at {file_path}' if name else f'{file_path} is not a file or directory'
    if not file_path.exists():
        raise ValidationError(not_exists)
    if not file_path.is_file():
        raise ValidationError(f'{file_path} is not a file')
    return file_path
# def _get_current_user_object_id(graph_client):
#     try:
#         current_user = graph_client.signed_in_user.get()
#         if current_user and current_user.object_id:  # pylint:disable=no-member
#             return current_user.object_id  # pylint:disable=no-member
#     except CloudError:
#         pass


# def _get_object_id_by_spn(graph_client, spn):
#     accounts = list(graph_client.service_principals.list(
#         filter=f"servicePrincipalNames/any(c:c eq '{spn}')"))
#     if not accounts:
#         logger.warning("Unable to find user with spn '%s'", spn)
#         return None
#     if len(accounts) > 1:
#         logger.warning("Multiple service principals found with spn '%s'. "
#                        "You can avoid this by specifying object id.", spn)
#         return None
#     return accounts[0].object_id


# def _get_object_id_by_upn(graph_client, upn):
#     accounts = list(graph_client.users.list(filter=f"userPrincipalName eq '{upn}'"))
#     if not accounts:
#         logger.warning("Unable to find user with upn '%s'", upn)
#         return None
#     if len(accounts) > 1:
#         logger.warning("Multiple users principals found with upn '%s'. "
#                        "You can avoid this by specifying object id.", upn)
#         return None
#     return accounts[0].object_id


# def _get_object_id_from_subscription(graph_client, subscription):
#     if not subscription:
#         return None

#     if subscription['user']:
#         if subscription['user']['type'] == 'user':
#             return _get_object_id_by_upn(graph_client, subscription['user']['name'])
#         if subscription['user']['type'] == 'servicePrincipal':
#             return _get_object_id_by_spn(graph_client, subscription['user']['name'])
#         logger.warning("Unknown user type '%s'", subscription['user']['type'])
#     else:
#         logger.warning('Current credentials are not from a user or service principal. '
#                        'Azure Key Vault does not work with certificate credentials.')
#     return None


# def _get_object_id(graph_client, subscription=None, spn=None, upn=None):
#     if spn:
#         return _get_object_id_by_spn(graph_client, spn)
#     if upn:
#         return _get_object_id_by_upn(graph_client, upn)
#     return _get_object_id_from_subscription(graph_client, subscription)


# def get_user_info(cmd):

#     profile = Profile(cli_ctx=cmd.cli_ctx)
#     cred, _, tenant_id = profile.get_login_credentials(
#         resource=cmd.cli_ctx.cloud.endpoints.active_directory_graph_resource_id)

#     graph_client = GraphRbacManagementClient(
#         cred,
#         tenant_id,
#         base_url=cmd.cli_ctx.cloud.endpoints.active_directory_graph_resource_id)
#     subscription = profile.get_subscription()

#     try:
#         object_id = _get_current_user_object_id(graph_client)
#     except GraphErrorException:
#         object_id = _get_object_id(graph_client, subscription=subscription)
#     if not object_id:
#         raise AzureResponseError('Cannot create vault.\nUnable to query active directory for information '
#                                  'about the current user.\nYou may try the --no-self-perms flag to '
#                                  'create a vault without permissions.')

#     return object_id, tenant_id
