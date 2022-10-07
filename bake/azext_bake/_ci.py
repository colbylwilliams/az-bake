# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

import os
from pathlib import Path

from azure.cli.core.azclierror import CLIError
from knack.log import get_logger

logger = get_logger(__name__)


def is_github_actions():
    ci = os.environ.get('CI', False)
    github_action = os.environ.get('GITHUB_ACTION', False)
    return ci and github_action


def get_github_repo_url():
    github_server_url = os.environ.get('GITHUB_SERVER_URL', None)
    github_repository = os.environ.get('GITHUB_REPOSITORY', None)
    if github_server_url and github_repository:
        return f'{github_server_url}/{github_repository}'
    return None


def get_github_token():
    token = os.environ.get('GITHUB_TOKEN', None)
    if not token:
        logger.warning('GITHUB_TOKEN environment variable not set. This is required for private repositories.')
        # raise CLIError('GITHUB_TOKEN environment variable not set')
    return token


def get_github_ref():
    return os.environ.get('GITHUB_REF', None)


def get_github_sha():
    return os.environ.get('GITHUB_SHA', None)


def is_devops_pipeline():
    return os.environ.get('TF_BUILD', False)


def get_devops_repo_url():
    return os.environ.get('BUILD_REPOSITORY_URI', None)


def get_devops_token():
    return os.environ.get('SYSTEM_ACCESSTOKEN', None)


def get_devops_ref():
    return os.environ.get('BUILD_SOURCEBRANCH', None)


def get_devops_sha():
    return os.environ.get('BUILD_SOURCEVERSION', None)


def get_repo():
    repo = {}
    if is_github_actions():
        logger.warning('Running in GitHub Action')
        repo['provider'] = 'github'

        if (token := get_github_token()):
            url = url.replace('https://', f'https://{token}@')

        repo['url'] = url
        repo['ref'] = get_github_ref()
        repo['sha'] = get_github_sha()

    elif is_devops_pipeline():
        logger.warning('Running in Azure DevOps Pipeline')
        repo['provider'] = 'devops'

        if (token := get_devops_token()):
            url = url.replace('https://', f'https://{token}@')

        repo['url'] = url
        repo['ref'] = get_devops_ref()
        repo['sha'] = get_devops_sha()
    else:
        raise CLIError('Could not determine CI environment. Currently only support GitHub Actions and Azure DevOps Pipelines')

    return repo
