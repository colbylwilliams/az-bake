# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

import requests
from azure.cli.core.util import should_disable_connection_verify
from knack.util import CLIError


def get_github_release(repo='az-bake', org='colbylwilliams', version=None, prerelease=False):

    if version and prerelease:
        raise CLIError(
            'usage error: can only use one of --version/-v | --pre')

    url = f'https://api.github.com/repos/{org}/{repo}/releases'

    if prerelease:
        version_res = requests.get(url, verify=not should_disable_connection_verify())
        version_json = version_res.json()

        version_prerelease = next((v for v in version_json if v['prerelease']), None)
        if not version_prerelease:
            raise CLIError(f'--pre no prerelease versions found for {org}/{repo}')

        return version_prerelease

    url += (f'/tags/{version}' if version else '/latest')

    version_res = requests.get(url, verify=not should_disable_connection_verify())

    if version_res.status_code == 404:
        raise CLIError(
            f'No release version exists for {org}/{repo}. '
            'Specify a specific prerelease version with --version '
            'or use latest prerelease with --pre')

    return version_res.json()


def github_release_version_exists(version, repo='az-bake', org='colbylwilliams'):

    version_url = f'https://api.github.com/repos/{org}/{repo}/releases/tags/{version}'
    version_res = requests.get(version_url, verify=not should_disable_connection_verify())

    return version_res.status_code < 400
