# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

from re import match

from azure.cli.core.util import CLIError
from knack.log import get_logger

logger = get_logger(__name__)

# pylint: disable=unused-argument,


def prefix_validator(cmd, ns):
    if not ns.prefix:
        raise CLIError('--prefix|-p must be a valid string')


def bake_source_version_validator(cmd, ns):
    if ns.version:
        if ns.prerelease:
            raise CLIError(
                'usage error: can only use one of --version/-v | --pre')
        ns.version = ns.version.lower()
        if ns.version[:1].isdigit():
            ns.version = 'v' + ns.version
        if not _is_valid_version(ns.version):
            raise CLIError(
                '--version/-v should be in format v0.0.0 do not include -pre suffix')

        from ._utils import github_release_version_exists

        if not github_release_version_exists(ns.version):
            raise CLIError(f'--version/-v {ns.version} does not exist')


def user_validator(cmd, ns):
    # Make sure these arguments are non-empty strings.
    # When they are accidentally provided as an empty string "", they won't take effect when filtering the role
    # assignments, causing all matched role assignments to be listed/deleted. For example,
    #   az role assignment delete --assignee ""
    # removes all role assignments under the subscription.
    if getattr(ns, 'user_id') == "":
        # Get option name, like user_id -> --user-id
        option_name = cmd.arguments['user_id'].type.settings['options_list'][0]
        raise CLIError(f'usage error: {option_name} can\'t be an empty string.')


def _is_valid_url(url):
    return match(
        r'^http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\), ]|(?:%[0-9a-fA-F][0-9a-fA-F]))+$', url) is not None


def _is_valid_version(version):
    return match(r'^v[0-9]+\.[0-9]+\.[0-9]+$', version) is not None
