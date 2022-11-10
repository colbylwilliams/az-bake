# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

from argcomplete.completers import DirectoriesCompleter, FilesCompleter
from azure.cli.core.commands.parameters import (file_type, get_location_type, get_resource_group_completion_list,
                                                tags_type)
from knack.arguments import CLIArgumentType

from ._completers import get_version_completion_list
from ._validators import (bake_source_version_validator, gallery_resource_id_validator, image_names_validator,
                          repository_path_validator, sandbox_resource_group_name_validator, yaml_out_validator)

# get_resource_group_completion_list,)


def load_arguments(self, _):

    # confirm_type = CLIArgumentType(
    #     help='Do not prompt for confirmation. WARNING: This is irreversible.',
    #     action='store_true',
    #     required=False,
    #     options_list=['--yes', '-y']
    # )

    sandbox_resource_group_name_type = CLIArgumentType(
        options_list=['--sandbox', '-sb', '-g'], configured_default='bake-sandbox',
        completer=get_resource_group_completion_list, validator=sandbox_resource_group_name_validator,
        help='Name of the sandbox resource group. You can configure the default using `az configure --defaults bake-sandbox=<name>`'
    )

    gallery_resource_id_type = CLIArgumentType(
        options_list=['--gallery', '-r'], configured_default='bake-gallery',
        completer=get_resource_group_completion_list, validator=gallery_resource_id_validator,
        help='Name or ID of a Azure Compute Gallery. You can configure the default using `az configure --defaults bake-gallery=<id>`'
    )

    # repository_path_type = CLIArgumentType(
    #     options_list=['--repository', '--repo'], type=file_type, validator=repository_path_validator,
    #     help='Path to the locally cloned repository.')

    # yaml_outfile_type validator also validates yaml_outdir_type and yaml_stdout_type
    yaml_outfile_type = CLIArgumentType(options_list=['--outfile'], completer=FilesCompleter(), validator=yaml_out_validator, help='When set, saves the output as the specified file path.')
    yaml_outdir_type = CLIArgumentType(options_list=['--outdir'], completer=DirectoriesCompleter(), help='When set, saves the output at the specified directory.')
    yaml_stdout_type = CLIArgumentType(options_list=['--stdout'], action='store_true', help='When set, prints all output to stdout instead of corresponding files.')

    with self.argument_context('bake upgrade') as c:
        c.argument('version', options_list=['--version', '-v'], help='Version (tag). Default: latest stable.',
                   validator=bake_source_version_validator, completer=get_version_completion_list)
        c.argument('prerelease', options_list=['--pre'], action='store_true',
                   help='Update to the latest template prerelease version.')

    with self.argument_context('bake sandbox create') as c:  # uses command level validator, param validators are ignored
        c.argument('sandbox_resource_group_name', sandbox_resource_group_name_type)
        c.argument('gallery_resource_id', gallery_resource_id_type)
        c.argument('location', get_location_type(self.cli_ctx))
        c.argument('tags', tags_type)

        c.argument('name_prefix', options_list=['--name-prefix', '--name', '-n'],
                   help='The prefix to use in the name of all resources created in the build sandbox. '
                   'For example if Contoso-Images is provided, the key vault, storage account, and vnet '
                   'will be named Contoso-Images-kv, contosoimagesstorage, and contoso-images-vent respectively.')

        c.argument('principal_id', options_list=['--principal-id', '--principal'],
                   help='The principal id of a service principal used to run az bake from a CI pipeline. '
                   'It will be given contributor role to sandbox resource group.')

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
        c.argument('local_templates', options_list=['--local-templates', '--local'], action='store_true', arg_group='Advanced',
                   help='Use local template file that was packaged with the cliinstead of downloading from GitHub.')

    for scope in ['bake sandbox validate', 'bake validate sandbox']:
        with self.argument_context(scope) as c:
            c.argument('sandbox_resource_group_name', sandbox_resource_group_name_type)
            c.argument('gallery_resource_id', gallery_resource_id_type)
            c.ignore('sandbox')
            c.ignore('gallery')

    with self.argument_context('bake repo') as c:  # uses command level validator, param validators are ignored
        c.argument('repository_path', options_list=['--repo-path', '--repo', '-r'], type=file_type,
                   help='Path to the locally cloned repository.')
        c.argument('image_names', options_list=['--images', '-i'], nargs='*',
                   help='Space separated list of images to bake.  Default: all images in repository.')
        # c.argument('is_ci', options_list=['--ci'], action='store_true', help='Run in CI mode.')
        c.argument('repository_url', options_list=['--repo-url'], arg_group='Repo', help='Repository url.')
        c.argument('repository_token', options_list=['--repo-token'], arg_group='Repo', help='Repository token.')
        c.argument('repository_revision', options_list=['--repo-revision'], arg_group='Repo', help='Repository revision.')
        c.ignore('is_ci')
        c.ignore('sandbox')
        c.ignore('gallery')
        c.ignore('images')
        c.ignore('repo')

    with self.argument_context('bake repo setup') as c:
        c.argument('repository_path', options_list=['--repo-path', '--repo'], type=file_type, default='./',
                   validator=repository_path_validator, help='Path to the locally cloned repository.')
        c.argument('sandbox_resource_group_name', sandbox_resource_group_name_type)
        c.argument('gallery_resource_id', gallery_resource_id_type)
        c.ignore('sandbox')
        c.ignore('gallery')

    # with self.argument_context('bake image') as c: # uses command level validator, param validators are ignored
    #     c.argument('sandbox_resource_group_name', sandbox_resource_group_name_type)
    #     c.argument('gallery_resource_id', gallery_resource_id_type)
    #     c.argument('image_path', options_list=['--image-path', '-i'], type=file_type, help='Path to image to bake.')
    #     c.argument('bake_yaml', options_list=['--bake-yaml', '-b'], type=file_type, help='Path to bake.yaml file.')
    #     c.ignore('sandbox')
    #     c.ignore('gallery')
    #     c.ignore('image')

    with self.argument_context('bake image create') as c:
        c.argument('image_name', options_list=['--name', '-n'], help='Name of the image to create.')
        c.argument('repository_path', options_list=['--repo-path', '--repo', '-r'], type=file_type, default='./',
                   validator=repository_path_validator, help='Path to the locally cloned repository.')
        # c.argument('outfile', yaml_outfile_type, default='./images/image.yml')
        # c.argument('outdir', yaml_outdir_type)
        # c.argument('stdout', yaml_stdout_type)

    with self.argument_context('bake yaml export') as c:
        c.argument('sandbox_resource_group_name', sandbox_resource_group_name_type)
        c.argument('gallery_resource_id', gallery_resource_id_type)
        c.argument('outfile', yaml_outfile_type, default='./bake.yml')
        c.argument('outdir', yaml_outdir_type)
        c.argument('stdout', yaml_stdout_type)
        c.ignore('sandbox')
        c.ignore('gallery')
        c.ignore('images')

    with self.argument_context('bake _builder') as c:  # uses command level validator, param validators are ignored
        c.ignore('sandbox')
        c.ignore('gallery')
        c.ignore('image')
        c.ignore('suffix')
