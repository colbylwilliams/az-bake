# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

import ipaddress
from re import match

from azure.cli.core.azclierror import (InvalidArgumentValueError,
                                       MutuallyExclusiveArgumentError,
                                       RequiredArgumentMissingError)
from azure.cli.core.commands.validators import validate_tags
from azure.cli.core.extension import get_extension
from knack.log import get_logger

from ._completers import get_default_location_from_sandbox_resource_group
from ._constants import tag_key
from ._github_utils import (get_github_latest_release_version,
                            github_release_version_exists)

logger = get_logger(__name__)

# pylint: disable=unused-argument,


def prefix_validator(cmd, ns):
    if not ns.prefix:
        raise InvalidArgumentValueError('--prefix|-p must be a valid string')


def templates_version_validator(cmd, ns):
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


def _is_valid_url(url):
    return match(
        r'^http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\), ]|(?:%[0-9a-fA-F][0-9a-fA-F]))+$', url) is not None


def _is_valid_version(version):
    return match(r'^v[0-9]+\.[0-9]+\.[0-9]+$', version) is not None


def none_or_empty(val):
    return val in ('', '""', "''") or val is None


def validate_sandbox_tags(ns):
    if ns.tags:
        validate_tags(ns)

    tags_dict = {} if ns.tags is None else ns.tags

    if ns.version:
        tags_dict.update({tag_key('version'): ns.version})
    if ns.prerelease:
        tags_dict.update({tag_key('prerelease'): ns.prerelease})

    ext = get_extension('bake')
    ext_version = ext.get_version()
    cur_version_str = f'v{ext_version}'

    tags_dict.update({tag_key('cli'): cur_version_str})

    ns.tags = tags_dict


def process_sandbox_create_namespace(cmd, ns):
    # validate_resource_prefix(cmd, ns)
    get_default_location_from_sandbox_resource_group(cmd, ns)
    templates_version_validator(cmd, ns)
    if none_or_empty(ns.vnet_address_prefix):
        raise InvalidArgumentValueError(f'--vnet-address-prefix/--vnet-prefix must be a valid CIDR prefix')

    for subnet in ['default', 'builders']:
        validate_subnet(cmd, ns, subnet, [ns.vnet_address_prefix])

    validate_sandbox_tags
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


def validate_subnet(cmd, ns, subnet, vnet_prefixes):
    subnet_name_option = f'--{subnet}-subnet-name/--{subnet}-subnet'
    subnet_prefix_option = f'--{subnet}-subnet-prefix/--{subnet}-prefix'

    subnet_name_arg = f'{subnet}_subnet_name'
    subnet_prefix_arg = f'{subnet}_subnet_address_prefix'

    subnet_name_val = getattr(ns, subnet_name_arg, None)
    if none_or_empty(subnet_name_val):
        raise InvalidArgumentValueError(f'{subnet_name_option} must have a value')

    subnet_prefix_val = getattr(ns, subnet_prefix_arg, None)
    if none_or_empty(subnet_prefix_val):
        raise InvalidArgumentValueError(f'{subnet_prefix_option} must be a valid CIDR prefix')

    # subnet_prefix_is_default = hasattr(getattr(ns, subnet_prefix_arg), 'is_default')

    vnet_networks = [ipaddress.ip_network(p) for p in vnet_prefixes]
    if not all(any(h in n for n in vnet_networks) for h in ipaddress.ip_network(subnet_prefix_val).hosts()):
        raise InvalidArgumentValueError(
            '{} {} is not within the vnet address space (prefixed: {})'.format(
                subnet_prefix_option, subnet_prefix_val, ', '.join(vnet_prefixes)))
