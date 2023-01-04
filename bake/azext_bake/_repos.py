# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------
# pylint: disable=too-many-instance-attributes

import os

from dataclasses import dataclass, field
from typing import Literal

from azure.cli.core.azclierror import CLIError


@dataclass
class CI:
    provider: Literal['github', 'devops'] = None
    url: str = None
    token: str = None
    ref: str = None
    revision: str = None

    @staticmethod
    def is_ci():
        is_actions = os.environ.get('CI', False) and os.environ.get('GITHUB_ACTION', False)
        is_devops = os.environ.get('TF_BUILD', False)
        return is_actions or is_devops

    def __init__(self) -> None:
        if os.environ.get('CI', False) and os.environ.get('GITHUB_ACTION', False):
            self.provider = 'github'
            self.token = os.environ.get('GITHUB_TOKEN', None)
            self.ref = os.environ.get('GITHUB_REF', None)
            self.revision = os.environ.get('GITHUB_SHA', None)

            github_server_url = os.environ.get('GITHUB_SERVER_URL', None)
            github_repository = os.environ.get('GITHUB_REPOSITORY', None)
            if github_server_url and github_repository:
                self.url = f'{github_server_url}/{github_repository}'
            else:
                raise CLIError('Could not determine GitHub repository url from environment variables.')

        elif os.environ.get('TF_BUILD', False):
            self.provider = 'devops'
            self.token = os.environ.get('SYSTEM_ACCESSTOKEN', None)
            self.ref = os.environ.get('BUILD_SOURCEBRANCH', None)
            self.revision = os.environ.get('BUILD_SOURCEVERSION', None)
            self.url = os.environ.get('BUILD_REPOSITORY_URI', None)
            if not self.url:
                raise CLIError('Could not determine Azure DevOps repository url from environment variables.')

        else:
            raise CLIError('Could not determine CI environment. '
                           'Currently only support GitHub Actions and Azure DevOps Pipelines')


@dataclass
class Repo:
    # required properties
    url: str
    provider: Literal['github', 'devops'] = field(init=False)
    org: str = field(init=False)
    repo: str = field(init=False)
    # optional properties
    project: str = field(default=None, init=False)
    token: str = None
    ref: str = None
    revision: str = None
    clone_url: str = None

    def _parse_devops_url(self, url):
        '''Parse an Azure DevOps repository git url into its parts'''
        # examples:
        # https://dev.azure.com/colbylwilliams/MyProject/_git/az-bake
        # https://colbylwilliams.visualstudio.com/DefaultCollection/MyProject/_git/az-bake
        # https://colbylwilliams@dev.azure.com/colbylwilliams/MyProject/_git/az-bake

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

        self.url = url
        self.org = parts[index].replace('.visualstudio.com', '')

        if parts[index + 1] == 'defaultcollection':
            index += 1

        self.project = parts[index + 1]
        self.repo = parts[index + 2]

    def _parse_github_url(self, url):
        '''Parse a GitHub repository git url into its parts'''
        # examples:
        # git://github.com/colbylwilliams/az-bake.git
        # https://github.com/colbylwilliams/az-bake.git
        # git@github.com:colbylwilliams/az-bake.git

        url = url.lower().replace('git@', 'https://').replace('git://', 'https://')\
            .replace('github.com:', 'github.com/')

        if url.endswith('.git'):
            url = url[:-4]

        parts = url.split('/')

        index = next((i for i, part in enumerate(parts) if 'github.com' in part), -1)

        if index == -1 or len(parts) < index + 3:
            raise CLIError(f'{url} is not a valid GitHub repository url')

        self.url = url
        self.org = parts[index + 1]
        self.repo = parts[index + 2]

    def __post_init__(self):
        if 'github.com' in self.url.lower():
            self.provider = 'github'
            self._parse_github_url(self.url)
            self.clone_url = self.url.replace('https://', f'https://gituser:{self.token}@') if self.token else self.url
        elif 'dev.azure.com' in self.url.lower() or 'visualstudio.com' in self.url.lower():
            self.provider = 'devops'
            self._parse_devops_url(self.url)
            self.clone_url = self.url.replace(
                'https://', f'https://azurereposuser:{self.token}@') if self.token else self.url
        else:
            raise CLIError(f'{self.url} is not a valid Azure DevOps or GitHub respository url')


if __name__ == '__main__':

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

        repository = Repo(url=test, token='mytoken')
        if repository.provider not in ['github', 'devops']:
            raise CLIError(f'{repository.provider} is not a valid provider')
        if repository.org != 'colbylwilliams':
            raise CLIError(f'{repository.org} is not a valid organization')
        if repository.provider == 'devops' and repository.project != 'myproject':
            raise CLIError(f'{repository.project} is not a valid project')
        if repository.repo != 'az-bake':
            raise CLIError(f'{repository.repo} is not a valid repository')
        if '@' in repository.url:
            raise CLIError(f'{repository.url} should not contain an @ symbol')
        print(repository)
    print('')
