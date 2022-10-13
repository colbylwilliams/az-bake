# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

import json
from pathlib import Path
from xml.dom import minidom
from xml.etree.ElementTree import Element, tostring

import yaml
from azure.cli.core.azclierror import (ClientRequestError, FileOperationError,
                                       MutuallyExclusiveArgumentError,
                                       ResourceNotFoundError, ValidationError)
from azure.cli.core.util import should_disable_connection_verify
from knack.log import get_logger

logger = get_logger(__name__)


def get_templates_path(folder=None):
    '''Get the path to the templates folder'''
    path = Path(__file__).resolve().parent / 'templates'
    return path / folder if folder else path


def get_yaml_file_path(dir, file, required=True):
    '''Get the path to a yaml or yml file in a directory'''
    dir_path = (dir if isinstance(dir, Path) else Path(dir)).resolve()

    if not dir_path.is_dir():
        if required:
            raise ValidationError(f'Directory for yaml/yml {file} not found at {dir}')
        return None

    yaml_path = dir_path / f'{file}.yaml'
    yml_path = dir_path / f'{file}.yml'

    yaml_isfile = yaml_path.is_file()
    yml_isfile = yml_path.is_file()

    if not yaml_isfile and not yml_isfile:
        if required:
            raise ValidationError(f'File {file}.yaml or {file}.yml not found in {dir}')
        return None
    elif yaml_isfile and yml_isfile:
        raise ValidationError(f'Found both {file}.yaml and {file}.yml in {dir} of repository. Only one {file} yaml file allowed')

    file_path = yaml_path if yaml_path.is_file() else yml_path

    return file_path


def get_yaml_file_contents(path):
    path = (path if isinstance(path, Path) else Path(path)).resolve()
    if not path.is_file():
        raise FileOperationError(f'Could not find yaml file at {path}')
    try:
        with open(path, 'r') as f:
            obj = yaml.safe_load(f)
    except OSError:  # FileNotFoundError introduced in Python 3
        raise FileOperationError(f'No such file or directory: {path}')
    except yaml.YAMLError as e:
        raise FileOperationError(f'Error while parsing yaml file:\n\n' + str(e))
    if obj is None:
        raise FileOperationError(f'Yaml file cannot be empty: {path}')
    return obj


def get_install_choco_dict(image):
    if 'install' not in image or 'choco' not in image['install']:
        return None

    install_path = get_templates_path('install')
    choco_index_path = install_path / 'choco.json'
    choco_index = {}
    with open(choco_index_path, 'r') as f:
        choco_index = json.load(f)

    choco = []
    for c in image['install']['choco']:
        logger.warning(f'Getting choco config for {c} type {type(c)}')
        if isinstance(c, str):
            if c in choco_index:
                choco.append(choco_index[c])
            else:
                choco.append({'id': c})
        elif isinstance(c, dict):
            choco.append(c)
        else:
            raise ValidationError(f'Invalid choco config {c} in image {image["name"]}')

    return choco


def get_choco_package_config(packages, indent=2):
    '''Get the chocolatey config file'''
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
