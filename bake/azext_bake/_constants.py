# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

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
IN_BUILDER = True if IN_BUILDER else False

REPO_DIR = Path(AZ_BAKE_REPO_VOLUME) if IN_BUILDER else Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = Path(AZ_BAKE_STORAGE_VOLUME) if IN_BUILDER else REPO_DIR / '.local' / 'storage'

OUTPUT_DIR = STORAGE_DIR / timestamp

if IN_BUILDER:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


BAKE_PLACEHOLDER = '###BAKE###'


PKR_BUILD_FILE = 'build.pkr.hcl'
PKR_VARS_FILE = 'variable.pkr.hcl'
PKR_AUTO_VARS_FILE = 'vars.auto.pkrvars.json'

TAG_PREFIX = 'hidden-bake:'

KEY_REQUIRED = 'required'
KEY_ALLOWED = 'allowed'

BAKE_REQUIRED_PROPERTIES = [
    'version',
    'sandbox',
    'gallery',
    # 'images'
]

# TODO: Add type and description to the properties for validaiton and hints

SANDBOX_REQUIRED_PROPERTIES = [
    'resourceGroup',
    'subscription',
    'virtualNetwork',
    'keyVault',
    'storageAccount',
    'identityId',
    'virtualNetworkResourceGroup',
    'defaultSubnet',
    'builderSubnet'
]
SANDBOX_ALLOWED_PROPERTIES = SANDBOX_REQUIRED_PROPERTIES + [
    'location'
]
SANDBOX_PROPERTIES = {
    KEY_REQUIRED: SANDBOX_REQUIRED_PROPERTIES,
    KEY_ALLOWED: SANDBOX_ALLOWED_PROPERTIES
}

GALLERY_REQUIRED_PROPERTIES = [
    'name',
    'resourceGroup'
]
GALLERY_ALLOWED_PROPERTIES = GALLERY_REQUIRED_PROPERTIES + [
    'subscription'
]
GALLERY_PROPERTIES = {
    KEY_REQUIRED: GALLERY_REQUIRED_PROPERTIES,
    KEY_ALLOWED: GALLERY_ALLOWED_PROPERTIES
}

IMAGE_COMMON_ALLOWED_PROPERTIES = [
    'publisher',
    'offer',
    'replicaLocations'
]
IMAGE_REQUIRED_PROPERTIES = IMAGE_COMMON_ALLOWED_PROPERTIES + [
    'name',
    'sku',
    'version',
    'os'
]
IMAGE_ALLOWED_PROPERTIES = IMAGE_REQUIRED_PROPERTIES + [
    'description',
    'install',
    'base'
]

IMAGE_INSTALL_PROPERTIES = {
    KEY_ALLOWED: ['script', 'choco', 'winget']
}

IMAGE_BASE_PROPERTIES = {
    KEY_REQUIRED: ['publisher', 'offer', 'sku', 'version'],
}

IMAGE_DEFAULT_BASE_WINDOWS = {
    'publisher': 'microsoftwindowsdesktop',
    'offer': 'windows-ent-cpc',
    'sku': 'win11-22h2-ent-cpc-m365',
    'version': 'latest'
}

BAKE_PROPERTIES = {
    KEY_REQUIRED: BAKE_REQUIRED_PROPERTIES,
    'sandbox': SANDBOX_PROPERTIES,
    # 'images': {
    #     KEY_ALLOWED: IMAGE_COMMON_ALLOWED_PROPERTIES
    # },
    'gallery': GALLERY_PROPERTIES
}

IMAGE_PROPERTIES = {
    KEY_REQUIRED: IMAGE_REQUIRED_PROPERTIES,
    KEY_ALLOWED: IMAGE_ALLOWED_PROPERTIES,
    'install': IMAGE_INSTALL_PROPERTIES,
    'base': IMAGE_BASE_PROPERTIES
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

PKR_VARS_MAP = {

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

PKR_PROVISIONER_CHOCO = f'''
  # Injected by az bake
  provisioner "powershell" {{
    environment_vars = ["chocolateyUseWindowsCompression=false"]
    inline = [
      "(new-object net.webclient).DownloadFile('https://chocolatey.org/install.ps1', 'C:/Windows/Temp/chocolatey.ps1')",
      "& C:/Windows/Temp/chocolatey.ps1"
    ]
  }}

  # Injected by az bake
  provisioner "file" {{
    source = "${{path.root}}/{CHOCO_PACKAGES_CONFIG_FILE}"
    destination = "C:/Windows/Temp/{CHOCO_PACKAGES_CONFIG_FILE}"
  }}

  # Injected by az bake
  provisioner "powershell" {{
    elevated_user     = build.User
    elevated_password = build.Password
    inline = [
      "choco install C:/Windows/Temp/{CHOCO_PACKAGES_CONFIG_FILE} --yes --no-progress"
    ]
  }}

  # Injected by az bake
  provisioner "file" {{
    source = "C:/ProgramData/chocolatey/logs/chocolatey.log"
    destination = "{OUTPUT_DIR}/chocolatey.log"
    direction = "download"
  }}
  {BAKE_PLACEHOLDER}'''

WINGET_SETTINGS_FILE = 'settings.json'

WINGET_INSTALLER_SRC = 'https://github.com/microsoft/winget-cli/releases/latest/download/Microsoft.DesktopAppInstaller_8wekyb3d8bbwe.msixbundle'
WINGET_INSTALLER_DEST = 'C:/Windows/Temp/Microsoft.DesktopAppInstaller_8wekyb3d8bbwe.msixbundle'
WINGET_SOURCE_SRC = 'https://winget.azureedge.net/cache/source.msix'
WINGET_SOURCE_DEST = 'C:/Windows/Temp/source.msix'

WINGET_SETTINGS_PATH = 'C:/Users/packer/AppData/Local/Packages/Microsoft.DesktopAppInstaller_8wekyb3d8bbwe/LocalState/settings.json'

WINGET_SETTINGS_JSON = f'''
{{
    "$schema": "https://aka.ms/winget-settings.schema.json",
    "installBehavior": {{
        "preferences": {{
            "scope": "machine"
        }}
    }}
}}
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
        run: az bake repo --verbose --repo .
    '''
