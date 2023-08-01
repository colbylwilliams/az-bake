# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------
# pylint: disable=logging-fstring-interpolation

import json
import os
import shutil
import subprocess
import sys
import uuid

from pathlib import Path
from typing import Any, Mapping, Sequence

from azure.cli.core.azclierror import ValidationError

from ._constants import (BAKE_PLACEHOLDER, PKR_PROVISIONER_CHOCO_MACHINE_INSTALL_LOG,
                         PKR_AUTO_VARS_FILE, PKR_BUILD_FILE, PKR_DEFAULT_VARS, PKR_PROVISIONER_CHOCO_INSTALL,
                         PKR_PROVISIONER_RESTART, PKR_PROVISIONER_UPDATE, LOCAL_USER_DIR,
                         PKR_PROVISIONER_WINGET_INSTALL, PKR_VARS_FILE, WINGET_SETTINGS_FILE, WINGET_SETTINGS_JSON,
                         PKR_PROVISIONER_CONSENTBEHAVIOR_LOWER, PKR_PROVISIONER_CHOCO_USER_INSTALL_SCRIPT)
from ._data import Gallery, Image, PowershellScript, Sandbox, WingetPackage, get_dict
from ._utils import get_logger, get_templates_path, get_choco_package_setup

logger = get_logger(__name__)

# indicates if the script is running in the docker container
in_builder = os.environ.get('ACI_IMAGE_BUILDER', False)


def check_packer_install(raise_error=True):
    '''Checks if packer is installed'''
    logger.info('Checking if packer is installed')
    packer = shutil.which('packer')
    installed = bool(packer)
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


def get_packer_vars(image: Image):
    '''Gets the available packer variables from the variable.pkr.hcl file'''
    try:
        args = _parse_command(['inspect', '-machine-readable', image.dir])
        logger.info(f'Running packer command: {" ".join(args)}')
        proc = subprocess.run(args, capture_output=True, check=True, text=True)
        if proc.stdout:
            logger.info(f'\n\n{proc.stdout}')
            return [v.strip().split('var.')[1].split(':')[0] for v in proc.stdout.split('\\n') if v.startswith('var.')]
        return PKR_DEFAULT_VARS
    except subprocess.CalledProcessError:
        return PKR_DEFAULT_VARS


def _clean_for_vars(obj, allowed_keys):
    '''Cleans an object for use as packer variables'''
    obj_dict = get_dict(obj)
    obj_vars = {}
    for k in obj_dict:
        if k in allowed_keys:
            obj_vars[k] = obj_dict[k]
    return obj_vars


def save_packer_vars_file(sandbox: Sandbox, gallery: Gallery, image: Image, additonal_vars: Mapping[str, Any] = None):
    '''Saves properties from image.yaml to a packer auto variables file'''
    logger.info(f'Saving packer auto variables file for {image.name}')
    pkr_vars = get_packer_vars(image)
    logger.info(f'Packer variables for {image.name}: {pkr_vars}')
    auto_vars = {}

    if additonal_vars:
        for v in pkr_vars:
            if v in additonal_vars and additonal_vars[v]:
                auto_vars[v] = additonal_vars[v]

    auto_vars['sandbox'] = _clean_for_vars(sandbox, PKR_DEFAULT_VARS['sandbox'])
    auto_vars['gallery'] = _clean_for_vars(gallery, PKR_DEFAULT_VARS['gallery'])
    auto_vars['image'] = _clean_for_vars(image, PKR_DEFAULT_VARS['image'])

    logger.info(f'Saving {image.name} packer auto variables:')
    for line in json.dumps(auto_vars, indent=4).splitlines():
        logger.info(line)

    with open(image.dir / PKR_AUTO_VARS_FILE, 'w', encoding='utf-8') as f:
        json.dump(auto_vars, f, ensure_ascii=False, indent=4, sort_keys=True)


def save_packer_vars_files(sandbox: Sandbox, gallery: Gallery, images: Sequence[Image],
                           additonal_vars: Mapping[str, Any] = None):
    '''Saves properties from each image.yaml to packer auto variables files'''
    for image in images:
        save_packer_vars_file(sandbox, gallery, image, additonal_vars)


def packer_init(image: Image):
    '''Executes the packer init command on an image'''
    logger.info(f'Executing packer init for {image.name}')
    args = _parse_command(['init', image.dir])
    logger.info(f'Running packer command: {" ".join(args)}')
    proc = subprocess.run(args, stdout=sys.stdout, stderr=sys.stderr, check=True, text=True)
    logger.info(f'Done executing packer init for {image.name}')
    return proc.returncode


def packer_build(image: Image):
    '''Executes the packer build command on an image'''
    logger.info(f'Executing packer build for {image.name}')
    args = _parse_command(['build', '-force', image.dir])
    if in_builder:
        args.insert(2, '-color=false')
    logger.info(f'Running packer command: {" ".join(args)}')
    proc = subprocess.run(args, stdout=sys.stdout, stderr=sys.stderr, check=True, text=True)
    logger.info(f'Done executing packer build for {image.name}')
    return proc.returncode


def packer_execute(image: Image):
    '''Executes the packer init and build commands on an image'''
    i = packer_init(image)
    return packer_build(image) if i == 0 else i


def copy_packer_files(image_dir: Path):
    '''Copies the packer files from the bake templates to the image directory unless they already exist'''
    logger.info(f'Copying packer files to {image_dir}')
    templates_dir = get_templates_path('packer')

    vars_file = image_dir / PKR_VARS_FILE
    build_file = image_dir / PKR_BUILD_FILE

    if vars_file.exists():
        logger.warning(f'Packer variables file already exists at {vars_file}')
    else:
        shutil.copy2(templates_dir / PKR_VARS_FILE, image_dir)

    if build_file.exists():
        logger.warning(f'Packer build file already exists at {build_file}')
        logger.warning('Provisioners will not be injected for the image.yaml install section')
        return False

    shutil.copy2(templates_dir / PKR_BUILD_FILE, image_dir)
    return True


def inject_update_provisioner(image_dir: Path):
    '''Injects the update provisioner into the packer build file'''
    _inject_provisioner(image_dir, PKR_PROVISIONER_UPDATE)


def inject_restart_provisioner(image_dir: Path):
    '''Injects the restart provisioner into the packer build file'''
    _inject_provisioner(image_dir, PKR_PROVISIONER_RESTART)


def inject_powershell_provisioner(image_dir: Path, powershell_scripts: Sequence[PowershellScript]):
    '''Injects the powershell provisioner into the packer build file'''

    current_index = 0
    inject_restart = False

    powershell_provisioner = '''
  # Injected by az bake
  provisioner "powershell" {
    elevated_user     = build.User
    elevated_password = build.Password
    scripts = [
'''

    for i, script in enumerate(powershell_scripts):
        current_index = i
        script_path = script.path
        powershell_provisioner += f'      "{script_path}"'

        if script.restart is True:
            inject_restart = True
            break

        if i < len(powershell_scripts) - 1:
            powershell_provisioner += ',\n'

    powershell_provisioner += f'''
    ]
  }}
  {BAKE_PLACEHOLDER}'''

    _inject_provisioner(image_dir, powershell_provisioner)

    if inject_restart:
        inject_restart_provisioner(image_dir)

        if current_index < len(powershell_scripts) - 1:
            inject_powershell_provisioner(image_dir, powershell_scripts[current_index + 1:])


def inject_choco_install_provisioners(image_dir: Path):
    '''Injects the chocolatey install provisioner into the packer build file'''
    _inject_provisioner(image_dir, PKR_PROVISIONER_CHOCO_INSTALL)


def inject_choco_user_script_provisioners(image_dir: Path):
    '''Injects the chocolatey user script provisioner into the packer build file'''
    _inject_provisioner(image_dir, PKR_PROVISIONER_CHOCO_USER_INSTALL_SCRIPT)


def inject_choco_user_consent_provisioners(image_dir: Path):
    '''Injects the chocolatey user script provisioner into the packer build file'''
    _inject_provisioner(image_dir, PKR_PROVISIONER_CONSENTBEHAVIOR_LOWER)


def inject_choco_machine_log_provisioners(image_dir: Path):
    '''Injects the chocolatey install provisioner into the packer build file'''
    _inject_provisioner(image_dir, PKR_PROVISIONER_CHOCO_MACHINE_INSTALL_LOG)


def inject_choco_machine_provisioners(image_dir: Path, choco_packages):
    '''Injects the chocolatey machine provisioner into the packer build file'''

    current_index = 0
    inject_restart = False

    choco_system_provisioner = '''
  # Injected by az bake
  provisioner "powershell" {
    elevated_user     = build.User
    elevated_password = build.Password
    inline = [
'''
    for i, choco_package in enumerate(choco_packages):
        current_index = i
        choco_system_provisioner += f'      "choco install {choco_package.id} {get_choco_package_setup(choco_package)}"'
        
        if choco_package.restart is True:
            inject_restart = True
            break
        if i < len(choco_packages) - 1:
            choco_system_provisioner += ',\n'

    choco_system_provisioner += f'''
    ]
  }}
  {BAKE_PLACEHOLDER}'''
    _inject_provisioner(image_dir, choco_system_provisioner)

    if inject_restart:
        inject_restart_provisioner(image_dir)

        if current_index < len(choco_packages) - 1:
            inject_choco_machine_provisioners(image_dir, choco_packages[current_index + 1:])


def inject_choco_user_provisioners(image_dir: Path, choco_packages):
    '''Injects the chocolatey user provisioner into the packer build file'''

    choco_user_provisioner = '''
  # Injected by az bake
  provisioner "powershell" {
    elevated_user     = build.User
    elevated_password = build.Password
    inline = [
      "Write-Host 'Setting up User installation via Active Setup'",
'''

    activesetup_id = uuid.uuid4()
    base_reg_key = 'HKLM:\\\\SOFTWARE\\\\Microsoft\\\\Active Setup\\\\Installed Components\\\\'

    for i, choco_package in enumerate(choco_packages):
        choco_str = get_choco_package_setup(choco_package)
        key_name = f'{i}{activesetup_id}'
        base_reg_key_newitem = f'      "New-Item \'{base_reg_key}\' -Name {key_name}'
        base_reg_key_property = f'      "New-ItemProperty \'{base_reg_key}{key_name}\''
        script_value = f'Powershell -File {LOCAL_USER_DIR}/Install-ChocoUser.ps1'
        stubpath_value = f'{script_value} -PackageId {choco_package.id} -PackageArguments \\"{choco_str}\\"'
        choco_user_provisioner += f'{base_reg_key_newitem} -Value \'AZ Bake {choco_package.id} Setup\'", \n'
        choco_user_provisioner += f'{base_reg_key_property} -Name \'StubPath\' -Value \'{stubpath_value}\'", \n'

    key_name = f'>9{activesetup_id}'
    base_reg_key_newitem = f'      "New-Item \'{base_reg_key}\' -Name \'{key_name}\''
    base_reg_key_property = f'      "New-ItemProperty \'{base_reg_key}{key_name}\''
    script_value = f'Powershell -File {LOCAL_USER_DIR}/Reset-AdminConsentBehavior.ps1'
    choco_user_provisioner += f'{base_reg_key_newitem} -Value \'AZ Bake Admin Behavior Setup\'", \n'
    choco_user_provisioner += f'{base_reg_key_property} -Name \'StubPath\' -Value \'{script_value}\'"\n'

    choco_user_provisioner += f'''
    ]
  }}
  {BAKE_PLACEHOLDER}'''
    _inject_provisioner(image_dir, choco_user_provisioner)


def inject_winget_provisioners(image_dir: Path, winget_packages: Sequence[WingetPackage]):
    '''Injects the winget provisioners into the packer build file'''

    logger.info(f'Creating file: {image_dir / WINGET_SETTINGS_FILE}')
    with open(image_dir / WINGET_SETTINGS_FILE, 'w', encoding='utf-8') as f:
        f.write(WINGET_SETTINGS_JSON)

    winget_install = f'''
{PKR_PROVISIONER_WINGET_INSTALL}

  # Injected by az bake
  provisioner "powershell" {{
    elevated_user     = build.User
    elevated_password = build.Password
    inline = [
'''

    for i, p in enumerate(winget_packages):
        winget_cmd = 'winget install '

        if p.any:  # user just specified a string, it could be a the moniker, name or id
            winget_cmd += f'{p.any} '
        elif p.id:
            winget_cmd += f'--id {p.id} '
        elif p.name:
            winget_cmd += f'--name {p.name} '
        elif p.moniker:
            winget_cmd += f'--moniker {p.moniker} '
        else:
            raise Exception('Invalid winget package configuration')

        if p.source:  # even if the user only specified a string, source could be in defaults
            winget_cmd += f'--source {p.source} '

        winget_cmd += '--accept-package-agreements --accept-source-agreements'

        winget_install += f'      "Write-Host \'>>> Running command: {winget_cmd}\'",\n'
        winget_install += f'      "{winget_cmd}"'

        if i < len(winget_packages) - 1:
            winget_install += ',\n'

    winget_install += f'''
    ]
  }}
  {BAKE_PLACEHOLDER}'''

    _inject_provisioner(image_dir, winget_install)


def _inject_provisioner(image_dir: Path, provisioner: str):
    '''Injects the provisioner into the packer build file'''

    build_file_path = image_dir / PKR_BUILD_FILE

    if not build_file_path.exists():
        raise ValidationError(f'Could not find {PKR_BUILD_FILE} file at {build_file_path}')
    if not build_file_path.is_file():
        raise ValidationError(f'{build_file_path} is not a file')

    # inject provisioner into build.pkr.hcl
    logger.info(f'Injecting provisioner into {build_file_path}')

    with open(build_file_path, 'r', encoding='utf-8') as f:
        pkr_build = f.read()

    if BAKE_PLACEHOLDER not in pkr_build:
        raise ValidationError(f'Could not find {BAKE_PLACEHOLDER} in {PKR_BUILD_FILE} at {build_file_path}')

    pkr_build = pkr_build.replace(BAKE_PLACEHOLDER, provisioner)

    with open(build_file_path, 'w', encoding='utf-8') as f:
        f.write(pkr_build)
