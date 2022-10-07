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
from knack.log import get_logger

from ._constants import PKR_AUTO_VARS_FILE, PKR_DEFAULT_VARS

logger = get_logger(__name__)

# indicates if the script is running in the docker container
in_builder = os.environ.get('ACI_IMAGE_BUILDER', False)


def check_packer_install(raise_error=True):
    '''Checks if packer is installed'''
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

    return args


def get_packer_vars(image):
    '''Gets the available packer variables from the variable.pkr.hcl file'''
    try:
        args = _parse_command(['inspect', '-machine-readable', image['path']])
        logger.info(f'Running packer command: {" ".join(args)}')
        proc = subprocess.run(args, capture_output=True, check=True, text=True)
        if proc.stdout:
            logger.info(f'\n\n{proc.stdout}')
            return [v.strip().split('var.')[1].split(':')[0] for v in proc.stdout.split('\\n') if v.startswith('var.')]
        return PKR_DEFAULT_VARS
    except subprocess.CalledProcessError:
        return PKR_DEFAULT_VARS


def save_packer_vars_file(image):
    '''Saves properties from image.yaml to a packer auto variables file'''
    pkr_vars = get_packer_vars(image)
    auto_vars = {}

    for v in pkr_vars:
        if v in image and image[v]:
            auto_vars[v] = image[v]

    logger.info(f'Saving {image["name"]} packer auto variables:')
    for line in json.dumps(auto_vars, indent=4).splitlines():
        logger.info(line)

    with open(Path(image['path']) / PKR_AUTO_VARS_FILE, 'w') as f:
        json.dump(auto_vars, f, ensure_ascii=False, indent=4, sort_keys=True)


def save_packer_vars_files(images):
    '''Saves properties from each image.yaml to packer auto variables files'''
    for image in images:
        save_packer_vars_file(image)


def packer_init(image):
    '''Executes the packer init command on an image'''
    logger.info(f'Executing packer init for {image["name"]}')
    args = _parse_command(['init', image['path']])
    logger.info(f'Running packer command: {" ".join(args)}')
    proc = subprocess.run(args, stdout=sys.stdout, stderr=sys.stderr, check=True, text=True)
    logger.info(f'Done executing packer init for {image["name"]}')
    return proc.returncode


def packer_build(image):
    '''Executes the packer build command on an image'''
    logger.info(f'Executing packer build for {image["name"]}')
    args = _parse_command(['build', '-force', image['path']])
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
