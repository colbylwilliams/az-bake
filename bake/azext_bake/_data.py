from dataclasses import MISSING, dataclass, field, fields
from pathlib import Path
from typing import List, Literal, Optional

from azure.cli.core.azclierror import ValidationError

from ._constants import IMAGE_DEFAULT_BASE_WINDOWS


def _snake_to_camel(name: str):
    parts = name.split('_')
    return parts[0] + ''.join(word.title() for word in parts[1:])


def _validate_data_object(data_type: type, obj: dict, path: Path = None, parent_key: str = None):
    '''Validates a dict data object against a dataclass type.
    Ensures all required fields are present and that no invalid fields are present.'''

    flds = fields(data_type)
    all_fields = [_snake_to_camel(f.name) for f in flds]
    req_fields = [_snake_to_camel(f.name) for f in flds if f.default is MISSING]
    # opt_fields = [f.name for f in flds if f.default is not MISSING]

    key_prefix = f'{parent_key}.' if parent_key else ''

    name = f'{path}' if path else f'{data_type.__name__} object'

    for k in req_fields:
        if k not in obj:
            raise ValidationError(f'{name} is missing required property: {key_prefix}{k}')
        if not obj[k]:
            raise ValidationError(f'{name} is missing a value for required property: {key_prefix}{k}')
        # TODO: Validate types
    for k in obj:
        if k not in all_fields and k not in ['file', 'dir']:
            raise ValidationError(f'{name} contains an invalid property: {key_prefix}{k}')


# --------------------------------
# Image > Install > Scripts
# --------------------------------


@dataclass
class PowershellScript:
    # required
    path: str
    # optional
    restart: bool = False

    def __init__(self, obj: dict, path: Path = None) -> None:
        _validate_data_object(PowershellScript, obj, path=path, parent_key='install.scripts.powershell')

        self.path = obj['path']
        self.restart = obj.get('restart', False)


@dataclass
class ImageInstallScripts:
    # optional
    powershell: List[PowershellScript] = field(default_factory=list)

    def __init__(self, obj: dict, path: Path = None) -> None:
        _validate_data_object(ImageInstallScripts, obj, path=path, parent_key='install.scripts')

        self.powershell = [PowershellScript({'path': s}, path) if isinstance(s, str) else PowershellScript(s, path) for s in obj['powershell']]


# --------------------------------
# Image > Install > Choco
# --------------------------------


@dataclass
class ChocoDefaults:
    # optional
    source: str = None
    install_arguments: str = None

    def __init__(self, obj: dict, path: Path = None) -> None:
        _validate_data_object(ChocoDefaults, obj, path=path, parent_key='install.choco.defaults')

        self.source = obj.get('source', None)
        self.install_arguments = obj.get('installArguments', None)


@dataclass
class ChocoPackage:
    # required
    id: str
    # optional
    source: Optional[str] = None
    version: Optional[str] = None
    install_arguments: Optional[str] = None
    package_parameters: Optional[str] = None
    user: bool = False

    def __init__(self, obj: dict, path: Path = None) -> None:
        _validate_data_object(ChocoPackage, obj, path=path, parent_key='install.choco')

        self.id = obj['id']
        self.source = obj.get('source', None)
        self.version = obj.get('version', None)
        self.install_arguments = obj.get('installArguments', None)
        self.package_parameters = obj.get('packageParameters', None)
        self.user = obj.get('user', False)


@dataclass
class ImageInstallChoco:
    # required
    packages: List[ChocoPackage] = field(default_factory=list)
    # optional
    defaults: Optional[ChocoDefaults] = None

    def __init__(self, obj: dict, path: Path = None) -> None:
        _validate_data_object(ImageInstallChoco, obj, path=path, parent_key='install.choco')

        self.packages = [ChocoPackage({'id': p}, path) if isinstance(p, str) else ChocoPackage(p, path) for p in obj['packages']]


# --------------------------------
# Image > Install > Winget
# --------------------------------


@dataclass
class WingetDefaults:
    # optional
    source: str = None

    def __init__(self, obj: dict, path: Path = None) -> None:
        _validate_data_object(WingetDefaults, obj, path=path, parent_key='install.winget.defaults')

        self.source = obj.get('source', None)


@dataclass
class WingetPackage:
    # required
    id: str = None
    name: str = None
    moniker: str = None
    any: str = None
    # optional
    source: str = None
    version: str = None

    def __init__(self, obj: dict, path: Path = None) -> None:
        _validate_data_object(WingetPackage, obj, path=path, parent_key='install.winget')

        self.id = obj.get('id', None)
        self.name = obj.get('name', None)
        self.moniker = obj.get('moniker', None)
        self.any = obj.get('any', None)

        # TODO: Validate that only one of id, name, moniker, any is set
        if not self.id and not self.name and not self.moniker and not self.any:
            raise ValidationError(f'{path} is missing required property: install.winget.id, install.winget.name, install.winget.moniker')

        self.source = obj.get('source', None)
        self.version = obj.get('version', None)


@dataclass
class ImageInstallWinget:
    # required
    packages: List[WingetPackage] = field(default_factory=list)
    # optional
    defaults: Optional[WingetDefaults] = None

    def __init__(self, obj: dict, path: Path = None) -> None:
        _validate_data_object(ImageInstallWinget, obj, path=path, parent_key='install.winget')

        self.packages = [WingetPackage({'any': p}, path) if isinstance(p, str) else WingetPackage(p, path) for p in obj['packages']]
        self.defaults = WingetDefaults(obj['defaults'], path) if 'defaults' in obj else None


# --------------------------------
# Image > Install
# --------------------------------


@dataclass
class ImageInstall:
    # optional
    scripts: Optional[ImageInstallScripts] = None
    choco: Optional[ImageInstallChoco] = None
    winget: Optional[ImageInstallWinget] = None

    def __init__(self, obj: dict, path: Path = None) -> None:
        _validate_data_object(ImageInstall, obj, path=path, parent_key='install')

        self.scripts = ImageInstallScripts(obj['scripts'], path) if 'scripts' in obj else None
        self.choco = ImageInstallChoco(obj['choco'], path) if 'choco' in obj else None
        self.winget = ImageInstallWinget(obj['winget'], path) if 'winget' in obj else None


# --------------------------------
# Image
# --------------------------------


@dataclass
class ImageBase:
    # required
    publisher: str
    offer: str
    sku: str
    # optional
    version: str = 'latest'

    def __init__(self, obj: dict, path: Path = None) -> None:
        _validate_data_object(ImageBase, obj, path=path, parent_key='base')

        self.publisher = obj['publisher']
        self.offer = obj['offer']
        self.sku = obj['sku']
        self.version = obj.get('version', 'latest')


@dataclass
class Image:
    '''Image definition'''
    # required
    publisher: str
    offer: str
    replica_locations: List[str]

    '''Image name, e.g. "Windows Server 2019 Datacenter"'''
    name: str
    sku: str
    version: str
    os: Literal['Windows', 'Linux']
    # optional
    description: str = None
    install: Optional[ImageInstall] = None
    base: ImageBase = None
    update: bool = True
    # cli
    # name: str = None
    dir: Path = None
    file: Path = None

    def __init__(self, obj: dict, path: Path = None) -> None:
        _validate_data_object(Image, obj, path=path)

        self.publisher = obj['publisher']
        self.offer = obj['offer']
        self.replica_locations = obj['replicaLocations']
        self.name = obj['name']
        self.sku = obj['sku']
        self.version = obj['version']
        self.os = obj['os']
        self.description = obj.get('description')
        self.install = ImageInstall(obj['install'], path) if 'install' in obj else None
        self.base = ImageBase(obj['base'], path) if 'base' in obj else ImageBase(IMAGE_DEFAULT_BASE_WINDOWS, path)
        self.update = obj.get('update', True)

        self.dir = path.parent
        self.file = path


# --------------------------------
# Sandbox
# --------------------------------


@dataclass
class Sandbox:
    # required
    resource_group: str
    subscription: str
    virtual_network: str
    virtual_network_resource_group: str
    default_subnet: str
    builder_subnet: str
    key_vault: str
    storage_account: str
    identity_id: str
    # optional
    location: str = None

    def __init__(self, obj: dict, path: Path = None) -> None:
        _validate_data_object(Sandbox, obj, path=path, parent_key='sandbox' if path else None)

        self.resource_group = obj['resourceGroup']
        self.subscription = obj['subscription']
        self.virtual_network = obj['virtualNetwork']
        self.virtual_network_resource_group = obj['virtualNetworkResourceGroup']
        self.default_subnet = obj['defaultSubnet']
        self.builder_subnet = obj['builderSubnet']
        self.key_vault = obj['keyVault']
        self.storage_account = obj['storageAccount']
        self.identity_id = obj['identityId']
        self.location = obj.get('location')

        # if not is_guid(bake_obj['sandbox']['subscription']):
        #     raise ValidationError('sandbox.subscription is not a valid GUID')

        # if not is_valid_resource_id(bake_obj['sandbox']['identityId']):
        #     raise ValidationError('sandbox.identityId is not a valid resource ID')


# --------------------------------
# Gallery
# --------------------------------


@dataclass
class Gallery:
    # required
    name: str
    resource_group: str
    # optional
    subscription: str = None
    # location: str

    def __init__(self, obj: dict, path: Path = None) -> None:
        _validate_data_object(Gallery, obj, path=path, parent_key='gallery' if path else None)

        self.name = obj['name']
        self.resource_group = obj['resourceGroup']
        self.subscription = obj.get('subscription')


# --------------------------------
# BakeConfig
# --------------------------------


@dataclass
class BakeConfig:
    file: Path
    # required
    version: int
    sandbox: Sandbox
    gallery: Gallery
    # cli
    name: str
    dir: Path

    def __init__(self, obj: dict, path: Path = None) -> None:
        _validate_data_object(BakeConfig, obj, path=path)

        self.file = obj['file']
        self.name = obj['name']
        self.dir = obj['dir']

        self.version = obj['version']
        self.sandbox = Sandbox(obj['sandbox'], path)
        self.gallery = Gallery(obj['gallery'], path)
