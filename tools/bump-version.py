# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

import argparse

from pathlib import Path
from re import search

from packaging.version import parse  # pylint: disable=unresolved-import

parser = argparse.ArgumentParser()
parser.add_argument('--major', action='store_true', help='bump major version')
parser.add_argument('--minor', action='store_true', help='bump minor version')
parser.add_argument('--notes', nargs='*', default=['Bug fixes and minor improvements.'], help='space seperated strings with release notes')

args = parser.parse_args()

major = args.major
minor = args.minor
notes = '+ {}'.format('\n* '.join(args.notes))

if major and minor:
    raise ValueError('usage error: --major | --minor')

patch = not minor and not major

version = None

path_root = Path(__file__).resolve().parent.parent
path_bake = path_root / 'bake'
path_builder = path_root / 'builder'

with open(path_bake / 'setup.py', 'r') as f:
    for line in f:
        if line.startswith('VERSION'):
            txt = str(line).rstrip()
            match = search(r'VERSION = [\'\"](.*)[\'\"]$', txt)
            if match:
                version = match.group(1)

if not version:
    raise ValueError('no version found in setup.py')

version_old = parse(version)

n_major = version_old.major + 1 if major else version_old.major
n_minor = 0 if major else version_old.minor + 1 if minor else version_old.minor
n_patch = 0 if major or minor else version_old.micro + 1

version_new = parse('{}.{}.{}'.format(n_major, n_minor, n_patch))


print('bumping version: {} -> {}'.format(version_old.public, version_new.public))

fmt_setup = 'VERSION = \'{}\''
fmt_readme = 'https://github.com/colbylwilliams/az-bake/releases/latest/download/bake-{}-py3-none-any.whl'
fmt_docker = 'https://github.com/colbylwilliams/az-bake/releases/latest/download/bake-{}-py3-none-any.whl'
fmt_consts = 'https://github.com/colbylwilliams/az-bake/releases/latest/download/bake-{}-py3-none-any.whl'
fmt_history = '{}\n++++++\n{}\n\n{}'


print('..updating setup.py')

with open(path_bake / 'setup.py', 'r') as f:
    setup = f.read()

if fmt_setup.format(version_old.public) not in setup:
    raise ValueError('version string not found in setup.py')

setup = setup.replace(fmt_setup.format(version_old.public), fmt_setup.format(version_new.public))

with open(path_bake / 'setup.py', 'w') as f:
    f.write(setup)


print('..updating HISTORY.rst')

with open(path_bake / 'HISTORY.rst', 'r') as f:
    history = f.read()

if version_old.public not in history:
    raise ValueError('version string not found in HISTORY.rst')

history = history.replace(version_old.public, fmt_history.format(version_new.public, notes, version_old.public))

with open(path_bake / 'HISTORY.rst', 'w') as f:
    f.write(history)


print('..updating Dockerfile')

with open(path_builder / 'Dockerfile', 'r') as f:
    docker = f.read()

if fmt_docker.format(version_old.public) not in docker:
    raise ValueError('version string not found in Dockerfile')

docker = docker.replace(fmt_docker.format(version_old.public), fmt_docker.format(version_new.public))

with open(path_builder / 'Dockerfile', 'w') as f:
    f.write(docker)


print('..updating README.md')

with open(path_root / 'README.md', 'r') as f:
    readme = f.read()

if fmt_readme.format(version_old.public) not in readme:
    raise ValueError('version string not found in README.md')

readme = readme.replace(fmt_readme.format(version_old.public), fmt_readme.format(version_new.public))

with open(path_root / 'README.md', 'w') as f:
    f.write(readme)


print('..updating _constants.py')

with open(path_bake / 'azext_bake' / '_constants.py', 'r') as f:
    constants = f.read()

if fmt_consts.format(version_old.public) not in constants:
    raise ValueError('version string not found in _constants.py')

constants = constants.replace(fmt_consts.format(version_old.public), fmt_consts.format(version_new.public))

with open(path_bake / 'azext_bake' / '_constants.py', 'w') as f:
    f.write(constants)
