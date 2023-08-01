# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------
# pylint: disable=line-too-long

import os

from datetime import datetime, timezone
from pathlib import Path

timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')

AZ_BAKE_IMAGE_BUILDER = 'AZ_BAKE_IMAGE_BUILDER'
AZ_BAKE_BUILD_IMAGE_NAME = 'AZ_BAKE_BUILD_IMAGE_NAME'
AZ_BAKE_IMAGE_BUILDER_VERSION = 'AZ_BAKE_IMAGE_BUILDER_VERSION'
AZ_BAKE_REPO_VOLUME = '/mnt/repo'
AZ_BAKE_STORAGE_VOLUME = '/mnt/storage'

IN_BUILDER = os.environ.get(AZ_BAKE_IMAGE_BUILDER)
IN_BUILDER = bool(IN_BUILDER)

REPO_DIR = Path(AZ_BAKE_REPO_VOLUME) if IN_BUILDER else Path(__file__).resolve().parent.parent.parent
# for dev
# REPO_DIR = Path(AZ_BAKE_REPO_VOLUME) if IN_BUILDER else Path(os.getcwd()).resolve()
STORAGE_DIR = Path(AZ_BAKE_STORAGE_VOLUME) if IN_BUILDER else REPO_DIR / '.local' / 'storage'

OUTPUT_DIR = STORAGE_DIR / (timestamp if IN_BUILDER else 'lastrun')
LOCAL_USER_DIR = 'C:/Users/Public/Documents'

if IN_BUILDER:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# for dev
# if not IN_BUILDER and OUTPUT_DIR.exists():
#     shutil.rmtree(OUTPUT_DIR)

# OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BAKE_PLACEHOLDER = '###BAKE###'


PKR_BUILD_FILE = 'build.pkr.hcl'
PKR_VARS_FILE = 'variable.pkr.hcl'
PKR_AUTO_VARS_FILE = 'vars.auto.pkrvars.json'

TAG_PREFIX = 'hidden-bake:'


IMAGE_DEFAULT_BASE_WINDOWS = {
    'publisher': 'microsoftwindowsdesktop',
    'offer': 'windows-ent-cpc',
    'sku': 'win11-22h2-ent-cpc-m365',
    'version': 'latest'
}


PKR_DEFAULT_VARS = {
    'image': [
        'name',
        'version',
        'replicaLocations',
        'os',
        'base'
    ],
    'gallery': [
        'name',
        'resourceGroup',
        'subscription'
    ],
    'sandbox': [
        'resourceGroup',
        'subscription',
        'virtualNetwork',
        'virtualNetworkResourceGroup',
        'defaultSubnet',
        'builderSubnet',
        'keyVault',
        'storageAccount',
        'identityId'
    ]
}


def tag_key(key):
    return f'{TAG_PREFIX}{key}'


DEFAULT_TAGS = {
    tag_key('cli-version'),
    tag_key('sandbox-version'),
    tag_key('sandbox-prerelease'),
    tag_key('buildResourceGroup'),
    tag_key('keyVault'),
    tag_key('virtualNetwork'),
    tag_key('virtualNetworkSubnet'),
    tag_key('virtualNetworkResourceGroup'),
    tag_key('subscription'),
    tag_key('storageAccount'),
    tag_key('subnetId'),
    tag_key('identityId'),
}

CHOCO_PACKAGES_CONFIG_FILE = 'packages.config'
CHOCO_PACKAGES_USER_CONFIG_FILE = 'user.packages.config'

PKR_PROVISIONER_UPDATE = f'''
  # Injected by az bake
  # https://github.com/rgl/packer-plugin-windows-update
  provisioner "windows-update" {{
  }}
  {BAKE_PLACEHOLDER}'''

PKR_PROVISIONER_RESTART = f'''
  # Injected by az bake
  provisioner "windows-restart" {{
    restart_timeout = "30m"
    pause_before    = "2m"
  }}
  {BAKE_PLACEHOLDER}'''

PKR_PROVISIONER_CHOCO_INSTALL = f'''
  # Injected by az bake
  provisioner "powershell" {{
    environment_vars = ["chocolateyUseWindowsCompression=false"]
    inline = [
      "(new-object net.webclient).DownloadFile('https://chocolatey.org/install.ps1', 'C:/Windows/Temp/chocolatey.ps1')",
      "& C:/Windows/Temp/chocolatey.ps1"
    ]
  }}
  {BAKE_PLACEHOLDER}'''


PKR_PROVISIONER_CHOCO_MACHINE_INSTALL_LOG = f'''
  # Injected by az bake
  provisioner "file" {{
    source = "C:/ProgramData/chocolatey/logs/chocolatey.log"
    destination = "{OUTPUT_DIR}/chocolatey.log"
    direction = "download"
  }}
  {BAKE_PLACEHOLDER}'''


PKR_PROVISIONER_CONSENTBEHAVIOR_LOWER = f'''
  # Injected by az bake
  provisioner "powershell" {{
    elevated_user     = build.User
    elevated_password = build.Password
    inline = [
      "Set-ItemProperty 'HKLM:\\\\SOFTWARE\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Policies\\\\System' -Name ConsentPromptBehaviorAdmin -Value 0 -type DWORD"
    ]
  }}
  {BAKE_PLACEHOLDER}'''


PKR_PROVISIONER_CHOCO_USER_INSTALL_SCRIPT = f'''
  # Injected by az bake
  provisioner "powershell" {{
    inline = [
      "(new-object net.webclient).DownloadFile('https://raw.githubusercontent.com/colbylwilliams/az-bake/main/examples/scripts/Install-ChocoUser.ps1', 'C:/Users/Public/Documents/Install-ChocoUser.ps1')",
      "(new-object net.webclient).DownloadFile('https://raw.githubusercontent.com/colbylwilliams/az-bake/main/examples/scripts/Reset-AdminConsentBehavior.ps1', 'C:/Users/Public/Documents/Reset-AdminConsentBehavior.ps1')",
    ]
  }}
  {BAKE_PLACEHOLDER}'''


WINGET_SETTINGS_FILE = 'settings.json'

WINGET_INSTALLER_SRC = 'https://github.com/microsoft/winget-cli/releases/latest/download/Microsoft.DesktopAppInstaller_8wekyb3d8bbwe.msixbundle'
WINGET_INSTALLER_DEST = 'C:/Windows/Temp/Microsoft.DesktopAppInstaller_8wekyb3d8bbwe.msixbundle'
WINGET_SOURCE_SRC = 'https://winget.azureedge.net/cache/source.msix'
WINGET_SOURCE_DEST = 'C:/Windows/Temp/source.msix'

WINGET_SETTINGS_PATH = 'C:/Users/packer/AppData/Local/Packages/Microsoft.DesktopAppInstaller_8wekyb3d8bbwe/LocalState/settings.json'

# pylint: disable=f-string-without-interpolation
WINGET_SETTINGS_JSON = '''{
    "$schema": "https://aka.ms/winget-settings.schema.json",
    "installBehavior": {
        "preferences": {
            "scope": "machine"
        }
    }
}
'''

PKR_PROVISIONER_WINGET_INSTALL = f'''
  # Injected by az bake
  provisioner "powershell" {{
    elevated_user     = build.User
    elevated_password = build.Password
    inline = [
      "Write-Host '>>> Downloading package: {WINGET_INSTALLER_SRC} to {WINGET_INSTALLER_DEST}'",
      "(new-object net.webclient).DownloadFile('{WINGET_INSTALLER_SRC}', '{WINGET_INSTALLER_DEST}')",
      "Write-Host '>>> Installing package: {WINGET_INSTALLER_DEST}'",
      "Add-AppxPackage -InstallAllResources -ForceTargetApplicationShutdown -ForceUpdateFromAnyVersion -Path '{WINGET_INSTALLER_DEST}'",
      # "Add-AppxProvisionedPackage -Online -SkipLicense -PackagePath '{WINGET_INSTALLER_DEST}'",

      "Write-Host '>>> Downloading package: {WINGET_SOURCE_SRC} to {WINGET_SOURCE_DEST}'",
      "(new-object net.webclient).DownloadFile('{WINGET_SOURCE_SRC}', '{WINGET_SOURCE_DEST}')",
      "Write-Host '>>> Installing package: {WINGET_SOURCE_DEST}'",
      "Add-AppxPackage -ForceTargetApplicationShutdown -ForceUpdateFromAnyVersion -Path '{WINGET_SOURCE_DEST}'",
      # "Add-AppxProvisionedPackage -Online -SkipLicense -PackagePath '{WINGET_SOURCE_DEST}'",

      "winget --info",

      "Write-Host '>>> Resetting winget source'",
      "winget source reset --force",
      "winget source list"
    ]
  }}

  # Injected by az bake
  provisioner "file" {{
    source = "${{path.root}}/{WINGET_SETTINGS_FILE}"
    destination = "{WINGET_SETTINGS_PATH}"
  }}
'''

GITHUB_PROVIDER_NAME = 'GitHub'
GITHUB_WORKFLOW_FILE = 'bake_images.yml'
GITHUB_WORKFLOW_DIR = '.github/workflows'
GITHUB_WORKFLOW_CONTENT = '''name: Bake Images

concurrency: ${{ github.ref }}

on:
  workflow_dispatch: # allow workflow to be manually triggered
  push:
    branches: [main]
    paths: # only run when bake.yml or image definitions change
    - 'bake.yml'
    - 'images/**'

jobs:
  bake:
    name: Bake Images
    runs-on: ubuntu-latest

    # uncomment to bake images only if '+bake' is in the commit message
    # if: "contains(join(github.event.commits.*.message), '+bake')"

    steps:
      - uses: actions/checkout@v3

      - name: Login to Azure
        run: az login --service-principal -u ${{ secrets.AZURE_CLIENT_ID }} -p ${{ secrets.AZURE_CLIENT_SECRET }} --tenant ${{ secrets.AZURE_TENANT_ID }}

      - name: Install az bake # get the latest version of az bake from the github releases and install it
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh release download --dir ${{ runner.temp }} --repo github.com/colbylwilliams/az-bake --pattern index.json
          az extension add --yes --source $(jq -r '.extensions.bake[0].downloadUrl' ${{ runner.temp }}/index.json)

      - name: Run az bake
        env:
          GITHUB_TOKEN: ${{ github.token }}
        run: az bake repo build --verbose --repo .
    '''

DEVOPS_PROVIDER_NAME = 'AzureDevOps'
DEVOPS_PIPELINE_FILE = 'azure-pipelines.yml'
DEVOPS_PIPELINE_DIR = '.azure'
DEVOPS_PIPELINE_CONTENT = '''name: Bake Images

trigger:
  batch: true
  branches:
    include:
      - main
  paths:
    include:
      - 'bake.yml'
      - 'images/**'

pool:
  vmImage: ubuntu-latest

steps:
  - script: az login --service-principal -u $AZURE_CLIENT_ID -p $AZURE_CLIENT_SECRET --tenant $AZURE_TENANT_ID
    displayName: Login to Azure
    env:
      AZURE_CLIENT_ID: $(AZURE_CLIENT_ID)
      AZURE_CLIENT_SECRET: $(AZURE_CLIENT_SECRET)
      AZURE_TENANT_ID: $(AZURE_TENANT_ID)

  - script: | # get the latest version of az bake from the github releases and install it
      curl -L https://github.com/colbylwilliams/az-bake/releases/latest/download/index.json > $AGENT_TEMPDIRECTORY/index.json
      az extension add --yes --source $(jq -r '.extensions.bake[0].downloadUrl' $AGENT_TEMPDIRECTORY/index.json)
    displayName: Install az bake

  - script: az bake repo build --verbose --repo .
    displayName: Run az bake
    env:
      SYSTEM_ACCESSTOKEN: $(System.AccessToken)
'''


BAKE_YAML_SCHEMA = '# yaml-language-server: $schema=https://github.com/colbylwilliams/az-bake/releases/latest/download/bake.schema.json'
IMAGE_YAML_SCHEMA = '# yaml-language-server: $schema=https://github.com/colbylwilliams/az-bake/releases/latest/download/image.schema.json'


IMAGE_YAML_COMMENTS = '''#  Required properties: (some may also be set in the images section of the bake.yaml file)
#
# - publisher: (string)
#       The name of the gallery image definition publisher.
# - offer: (string)
#       The name of the gallery image definition offer
# - replicaLocations: (array using - notation)
#       The target regions where the Image Version is going to be replicated to
# - sku: (string)
#       The name of the gallery image definition SKU
# - version: (string)
#       Version number for the image (ex. 1.0.0)
# - os: (string)
#       Windows or Linux.  For Dev Box, only Windows is supported

#  Optional properties: (may also be set in the images section of the bake.yaml file)
#
# - description: (string)
#       The description of this gallery image definition resource

'''
