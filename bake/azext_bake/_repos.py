# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

import os

from azure.cli.core.azclierror import CLIError
from knack.log import get_logger

logger = get_logger(__name__)


# ----------------
# Repository URLs
# ----------------

def _is_github_url(url) -> bool:
    return 'github.com' in url.lower()


def _is_devops_url(url) -> bool:
    return 'dev.azure.com' in url.lower() or 'visualstudio.com' in url.lower()


def _parse_github_url(url) -> dict:
    '''Parse a GitHub repository git url into its parts'''
    # examples:
    # git://github.com/colbylwilliams/az-bake.git
    # https://github.com/colbylwilliams/az-bake.git
    # git@github.com:colbylwilliams/az-bake.git

    if not _is_github_url(url):
        raise CLIError(f'{url} is not a valid GitHub repository url')

    url = url.lower().replace('git@', 'https://').replace('git://', 'https://').replace('github.com:', 'github.com/')

    if url.endswith('.git'):
        url = url[:-4]

    parts = url.split('/')

    index = next((i for i, part in enumerate(parts) if 'github.com' in part), -1)

    if index == -1 or len(parts) < index + 3:
        raise CLIError(f'{url} is not a valid GitHub repository url')

    repo = {
        'provider': 'github',
        'url': url,
        'org': parts[index + 1],
        'repo': parts[index + 2]
    }

    return repo


def _parse_devops_url(url) -> dict:
    '''Parse an Azure DevOps repository git url into its parts'''
    # examples:
    # https://dev.azure.com/colbylwilliams/MyProject/_git/az-bake
    # https://colbylwilliams.visualstudio.com/DefaultCollection/MyProject/_git/az-bake
    # https://colbylwilliams@dev.azure.com/colbylwilliams/MyProject/_git/az-bake

    if not _is_devops_url(url):
        raise CLIError(f'{url} is not a valid Azure DevOps respository url')

    url = url.lower().replace('git@ssh', 'https://').replace(':v3/', '/')

    if '@dev.azure.com' in url:
        url = 'https://dev.azure.com' + url.split('@dev.azure.com')[1]

    if url.endswith('.git'):
        url = url[:-4]

    parts = url.split('/')

    index = next((i for i, part in enumerate(parts) if 'dev.azure.com' in part or 'visualstudio.com' in part), -1)

    if index == -1:
        raise CLIError(f'{url} is not a valid Azure DevOps respository url')

    if '_git' in parts:
        parts.pop(parts.index('_git'))
    else:
        last = parts[-1]
        url = url.replace(f'/{last}', f'/_git/{last}')

    if 'dev.azure.com' in parts[index]:
        index += 1

    if len(parts) < index + 3:
        raise CLIError(f'{url} is not a valid Azure DevOps respository url')

    repo = {
        'provider': 'devops',
        'url': url,
        'org': parts[index].replace('.visualstudio.com', '')
    }

    if parts[index + 1] == 'defaultcollection':
        index += 1

    repo['project'] = parts[index + 1]
    repo['repo'] = parts[index + 2]

    return repo


def parse_repo_url(url) -> dict:
    '''Parse a repository git url into its parts. Supports GitHub and Azure DevOps'''

    if _is_github_url(url):
        return _parse_github_url(url)

    if _is_devops_url(url):
        return _parse_devops_url(url)

    raise CLIError(f'{url} is not a valid repository url')

# ----------------
# CI Environment
# ----------------


# GitHub Actions


def _is_github_actions():
    ci = os.environ.get('CI', False)
    github_action = os.environ.get('GITHUB_ACTION', False)
    return ci and github_action


def _get_github_repo_url():
    github_server_url = os.environ.get('GITHUB_SERVER_URL', None)
    github_repository = os.environ.get('GITHUB_REPOSITORY', None)
    if github_server_url and github_repository:
        return f'{github_server_url}/{github_repository}'
    return None


def _get_github_token():
    token = os.environ.get('GITHUB_TOKEN', None)
    if not token:
        logger.warning('GITHUB_TOKEN environment variable not set. This is required for private repositories.')
        # raise CLIError('GITHUB_TOKEN environment variable not set')
    return token


def _get_github_ref():
    return os.environ.get('GITHUB_REF', None)


def _get_github_sha():
    return os.environ.get('GITHUB_SHA', None)


def _is_devops_pipeline():
    return os.environ.get('TF_BUILD', False)


# DevOps Pipeline


def _get_devops_repo_url():
    return os.environ.get('BUILD_REPOSITORY_URI', None)


def _get_devops_token():
    token = os.environ.get('SYSTEM_ACCESSTOKEN', None)
    if not token:
        logger.warning('SYSTEM_ACCESSTOKEN environment variable not set. This is required for private repositories.')
        # raise CLIError('SYSTEM_ACCESSTOKEN environment variable not set')
    return token


def _get_devops_ref():
    return os.environ.get('BUILD_SOURCEBRANCH', None)


def _get_devops_sha():
    return os.environ.get('BUILD_SOURCEVERSION', None)


def is_ci():
    return _is_github_actions() or _is_devops_pipeline()


def get_repo():

    if _is_github_actions():
        logger.warning('Running in GitHub Action')

        url = _get_github_repo_url()
        repo = _parse_github_url(url)

        # if (token := _get_github_token()):
        #     repo['url'] = repo['url'].replace('https://', f'https://{token}@')

        repo['token'] = _get_github_token()
        repo['ref'] = _get_github_ref()
        repo['sha'] = _get_github_sha()

    elif _is_devops_pipeline():
        logger.warning('Running in Azure DevOps Pipeline')

        url = _get_devops_repo_url()
        repo = _parse_devops_url(url)

        # if (token := _get_devops_token()):
        #     repo['url'] = repo['url'].replace('https://', f'https://{token}@')

        repo['token'] = _get_devops_token()
        repo['ref'] = _get_devops_ref()
        repo['sha'] = _get_devops_sha()
    else:
        raise CLIError('Could not determine CI environment. Currently only support GitHub Actions and Azure DevOps Pipelines')

    return repo


if __name__ == '__main__':

    import json

    test_urls = [
        'git://github.com/colbylwilliams/az-bake.git',
        'https://github.com/colbylwilliams/az-bake.git',
        'git@github.com:colbylwilliams/az-bake.git',
        'https://dev.azure.com/colbylwilliams/MyProject/_git/az-bake',
        'https://colbylwilliams.visualstudio.com/DefaultCollection/MyProject/_git/az-bake',
        'https://user@dev.azure.com/colbylwilliams/MyProject/_git/az-bake'
    ]

    print('')
    for test in test_urls:
        repo = parse_repo_url(test)
        if repo['provider'] not in ['github', 'devops']:
            raise CLIError(f'{repo["provider"]} is not a valid provider')
        if repo['org'] != 'colbylwilliams':
            raise CLIError(f'{repo["org"]} is not a valid organization')
        if repo['provider'] == 'devops' and repo['project'] != 'myproject':
            raise CLIError(f'{repo["project"]} is not a valid project')
        if repo['repo'] != 'az-bake':
            raise CLIError(f'{repo["repo"]} is not a valid repository')
        if '@' in repo['url']:
            raise CLIError(f'{repo["url"]} should not contain an @ symbol')
        print(test)
        print(json.dumps(repo, indent=4))
    print('')
