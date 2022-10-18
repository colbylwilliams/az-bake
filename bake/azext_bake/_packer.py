# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from azure.cli.core.azclierror import ValidationError

from ._constants import (BAKE_PLACEHOLDER, CHOCO_PACKAGES_CONFIG_FILE,
                         PKR_AUTO_VARS_FILE, PKR_BUILD_FILE, PKR_DEFAULT_VARS,
                         PKR_PROVISIONER_CHOCO, PKR_PROVISIONER_WINGET_INSTALL,
                         PKR_VARS_FILE, WINGET_SETTINGS_FILE,
                         WINGET_SETTINGS_JSON)
from ._utils import get_logger, get_templates_path

logger = get_logger(__name__)

# indicates if the script is running in the docker container
in_builder = os.environ.get('ACI_IMAGE_BUILDER', False)


def check_packer_install(raise_error=True):
    '''Checks if packer is installed'''
    logger.info('Checking if packer is installed')
    packer = shutil.which('packer')
    installed = True if packer else False
    if not installed and raise_error:
        raise ValidationError('Packer is not installed. Please install packer and try again.')
    return installed


def _parse_command(command):
    '''Parses a command (string or list of args), adds the required arguments, and replaces executable with full path'''
    if isinstance(command, list):
        args = command
    elif isinstance(command, str):
        args = command.split()
    else:
        raise ValueError(f'command must be a string or list, not {type(command)}')

    packer = shutil.which('packer')

    if args[0] == 'packer':
        args.pop(0)

    if args[0] != packer:
        args = [packer] + args

    # convert Path objects to strings
    for i, arg in enumerate(args):
        if isinstance(arg, Path):
            args[i] = str(arg)

    return args


def get_packer_vars(image):
    '''Gets the available packer variables from the variable.pkr.hcl file'''
    try:
        args = _parse_command(['inspect', '-machine-readable', image['dir']])
        logger.info(f'Running packer command: {" ".join(args)}')
        proc = subprocess.run(args, capture_output=True, check=True, text=True)
        if proc.stdout:
            logger.info(f'\n\n{proc.stdout}')
            return [v.strip().split('var.')[1].split(':')[0] for v in proc.stdout.split('\\n') if v.startswith('var.')]
        return PKR_DEFAULT_VARS
    except subprocess.CalledProcessError:
        return PKR_DEFAULT_VARS


def _clean_for_vars(obj, allowed_keys):
    obj_vars = {}
    for k in obj:
        if k in allowed_keys:
            obj_vars[k] = obj[k]
    return obj_vars


def save_packer_vars_file(sandbox, gallery, image, additonal_vars=None):
    '''Saves properties from image.yaml to a packer auto variables file'''
    logger.info(f'Saving packer auto variables file for {image["name"]}')
    pkr_vars = get_packer_vars(image)
    logger.info(f'Packer variables for {image["name"]}: {pkr_vars}')
    auto_vars = {}

    if additonal_vars:
        for v in pkr_vars:
            if v in additonal_vars and additonal_vars[v]:
                auto_vars[v] = additonal_vars[v]

    auto_vars['sandbox'] = _clean_for_vars(sandbox, PKR_DEFAULT_VARS['sandbox'])
    auto_vars['gallery'] = _clean_for_vars(gallery, PKR_DEFAULT_VARS['gallery'])
    auto_vars['image'] = _clean_for_vars(image, PKR_DEFAULT_VARS['image'])

    logger.info(f'Saving {image["name"]} packer auto variables:')
    for line in json.dumps(auto_vars, indent=4).splitlines():
        logger.info(line)

    with open(image['dir'] / PKR_AUTO_VARS_FILE, 'w') as f:
        json.dump(auto_vars, f, ensure_ascii=False, indent=4, sort_keys=True)


def save_packer_vars_files(sandbox, gallery, images, additonal_vars=None):
    '''Saves properties from each image.yaml to packer auto variables files'''
    for image in images:
        save_packer_vars_file(sandbox, gallery, image, additonal_vars)


def packer_init(image):
    '''Executes the packer init command on an image'''
    logger.info(f'Executing packer init for {image["name"]}')
    args = _parse_command(['init', image['dir']])
    logger.info(f'Running packer command: {" ".join(args)}')
    proc = subprocess.run(args, stdout=sys.stdout, stderr=sys.stderr, check=True, text=True)
    logger.info(f'Done executing packer init for {image["name"]}')
    return proc.returncode


def packer_build(image):
    '''Executes the packer build command on an image'''
    logger.info(f'Executing packer build for {image["name"]}')
    args = _parse_command(['build', '-force', image['dir']])
    if in_builder:
        args.insert(2, '-color=false')
    logger.info(f'Running packer command: {" ".join(args)}')
    proc = subprocess.run(args, stdout=sys.stdout, stderr=sys.stderr, check=True, text=True)
    logger.info(f'Done executing packer build for {image["name"]}')
    return proc.returncode


def packer_execute(image):
    '''Executes the packer init and build commands on an image'''
    i = packer_init(image)
    return packer_build(image) if i == 0 else i


def copy_packer_files(image_dir):
    '''Copies the packer files from the bake templates to the image directory'''
    logger.info(f'Copying packer files to {image_dir}')
    templates_dir = get_templates_path('packer')
    shutil.copy2(templates_dir / PKR_BUILD_FILE, image_dir)
    shutil.copy2(templates_dir / PKR_VARS_FILE, image_dir)


def inject_choco_provisioners(image_dir, config_xml):
    '''Injects the chocolatey provisioners into the packer build file'''
    # create the choco packages config file
    logger.info(f'Creating file: {image_dir / CHOCO_PACKAGES_CONFIG_FILE}')
    with open(image_dir / CHOCO_PACKAGES_CONFIG_FILE, 'w') as f:
        f.write(config_xml)

    build_file_path = image_dir / PKR_BUILD_FILE

    if not build_file_path.exists():
        raise ValidationError(f'Could not find {PKR_BUILD_FILE} file at {build_file_path}')
    if not build_file_path.is_file():
        raise ValidationError(f'{build_file_path} is not a file')

    # inject chocolatey install into build.pkr.hcl
    logger.info(f'Injecting chocolatey install provisioners into {build_file_path}')

    with open(build_file_path, 'r') as f:
        pkr_build = f.read()

    if BAKE_PLACEHOLDER not in pkr_build:
        raise ValidationError(f'Could not find {BAKE_PLACEHOLDER} in {PKR_BUILD_FILE} at {build_file_path}')

    pkr_build = pkr_build.replace(BAKE_PLACEHOLDER, PKR_PROVISIONER_CHOCO)

    with open(build_file_path, 'w') as f:
        f.write(pkr_build)


def inject_winget_provisioners(image_dir, winget_packages):
    '''Injects the winget provisioners into the packer build file'''

    logger.info(f'Creating file: {image_dir / WINGET_SETTINGS_FILE}')
    with open(image_dir / WINGET_SETTINGS_FILE, 'w') as f:
        f.write(WINGET_SETTINGS_JSON)

    winget_install = f'''
{PKR_PROVISIONER_WINGET_INSTALL}

  # Injected by az bake
  provisioner "powershell" {{
    inline = [
'''
    for i, p in enumerate(winget_packages):
        winget_cmd = f'winget install '
        if 'ANY' in p:
            winget_cmd += f'{p["ANY"]} '
        else:
            for a in ['id', 'name', 'moniker', 'version', 'source']:
                if a in p:
                    winget_cmd += f'--{a} {p[a]} '
        winget_cmd += '--accept-package-agreements --accept-source-agreements'

        winget_install += f'      "Write-Host \'>>> Running command: {winget_cmd}\'",\n'
        winget_install += f'      "{winget_cmd}"'

        if i < len(winget_packages) - 1:
            winget_install += ',\n'

    winget_install += f'''
    ]
  }}
  {BAKE_PLACEHOLDER}'''

    build_file_path = image_dir / PKR_BUILD_FILE

    if not build_file_path.exists():
        raise ValidationError(f'Could not find {PKR_BUILD_FILE} file at {build_file_path}')
    if not build_file_path.is_file():
        raise ValidationError(f'{build_file_path} is not a file')

    # inject winget install into build.pkr.hcl
    logger.info(f'Injecting winget install provisioners into {build_file_path}')

    with open(build_file_path, 'r') as f:
        pkr_build = f.read()

    if BAKE_PLACEHOLDER not in pkr_build:
        raise ValidationError(f'Could not find {BAKE_PLACEHOLDER} in {PKR_BUILD_FILE} at {build_file_path}')

    pkr_build = pkr_build.replace(BAKE_PLACEHOLDER, winget_install)

    with open(build_file_path, 'w') as f:
        f.write(pkr_build)
