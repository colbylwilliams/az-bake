# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

from azure.cli.core.commands.parameters import (
    file_type, get_location_type, get_resource_group_completion_list,
    tags_type)
from knack.arguments import CLIArgumentType

from ._completers import get_version_completion_list
from ._validators import bake_source_version_validator

# get_resource_group_completion_list,)


def load_arguments(self, _):

    # confirm_type = CLIArgumentType(
    #     help='Do not prompt for confirmation. WARNING: This is irreversible.',
    #     action='store_true',
    #     required=False,
    #     options_list=['--yes', '-y']
    # )

    sandbox_resource_group_name_type = CLIArgumentType(
        options_list=['--resource-group', '--sandbox', '-g'],
        completer=get_resource_group_completion_list,
        # id_part='resource_group',
        help="Name of the sandbox resource group. You can configure the default using `az configure --defaults bake-sandbox=<name>`",
        configured_default='bake-sandbox',
    )

    with self.argument_context('bake upgrade') as c:
        c.argument('version', options_list=['--version', '-v'], help='Version (tag). Default: latest stable.',
                   validator=bake_source_version_validator, completer=get_version_completion_list)
        c.argument('prerelease', options_list=['--pre'], action='store_true',
                   help="The id of the user. If value is 'me', the identity is taken from the authentication "
                   "context.")

    for scope in ['bake sandbox']:
        with self.argument_context(scope) as c:
            c.argument('sandbox_resource_group_name', sandbox_resource_group_name_type)

    # sandbox create uses a command level validator, param validators will be ignored
    with self.argument_context('bake sandbox create') as c:
        c.argument('location', get_location_type(self.cli_ctx))
        c.argument('tags', tags_type)

        c.argument('name_prefix', options_list=['--name-prefix', '--name', '-n'],
                   help='The prefix to use in the name of all resources created in the build sandbox. '
                   'For example if Contoso-Images is provided, the key vault, storage account, and vnet '
                   'will be named Contoso-Images-kv, contosoimagesstorage, and contoso-images-vent respectively.')
        c.argument('principal_id', options_list=['--principal-id', '--principal'],
                   help='The principal id of a service principal used in the image build pipeline. '
                   'It will be givin contributor role to sandbox resource group, and the appropriate '
                   'permissions on the key vault and storage account')

        # c.argument('virtual_network_name', required=False,
        #            options_list=['--vnet-name', '--vnet'],
        #            help='The name to use when creating the sandbox virtual network. Defaults to use the name prefix.')
        c.argument('vnet_address_prefix', default='10.0.0.0/24', arg_group='Network',
                   options_list=['--vnet-address-prefix', '--vnet-prefix'],
                   help='The CIDR prefix to use when creating a new VNet.')

        c.argument('default_subnet_name', default='default', arg_group='Network',
                   options_list=['--default-subnet-name', '--default-subnet'],
                   help='The name to use when creating the subnet for the temporary VMs and private endpoints')
        c.argument('default_subnet_address_prefix', default='10.0.0.0/25', arg_group='Network',
                   options_list=['--default-subnet-prefix', '--default-prefix'],
                   help='The CIDR prefix to use when creating the subnet for the temporary VMs and private endpoints.')

        c.argument('builders_subnet_name', default='builders', arg_group='Network',
                   options_list=['--builders-subnet-name', '--builders-subnet'],
                   help='The name to use when creating the subnet for the ACI containers that execute Packer')
        c.argument('builders_subnet_address_prefix', default='10.0.0.128/25', arg_group='Network',
                   options_list=['--builders-subnet-prefix', '--builders-prefix'],
                   help='The CIDR prefix to use when creating the subnet for the ACI containers that execute Packer.')

        c.argument('version', options_list=['--version', '-v'], arg_group='Advanced',
                   completer=get_version_completion_list,
                   help='Sandbox template release version. Default: latest stable.')
        c.argument('prerelease', options_list=['--pre'], action='store_true', arg_group='Advanced',
                   help='Deploy latest template prerelease version.')
        c.argument('templates_url', arg_group='Advanced', help='URL to custom templates.json file.')
        c.argument('template_file', arg_group='Advanced', type=file_type, help='Path to custom sandbox arm/bicep template.')

    # with self.argument_context('bake user check') as c:
    #     c.argument('user', options_list=['--user', '-u'],
    #                help='User ')
