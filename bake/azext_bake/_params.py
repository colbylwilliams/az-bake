# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

from knack.arguments import CLIArgumentType

from ._validators import bake_source_version_validator


def load_arguments(self, _):

    confirm_type = CLIArgumentType(
        help='Do not prompt for confirmation. WARNING: This is irreversible.',
        action='store_true',
        required=False,
        options_list=['--yes', '-y']
    )

    with self.argument_context('bake upgrade') as c:
        c.argument('version', options_list=['--version', '-v'], help='Version (tag). Default: latest stable.',
                   validator=bake_source_version_validator)
        c.argument('prerelease', options_list=['--pre'], action='store_true',
                   help="The id of the user. If value is 'me', the identity is taken from the authentication "
                   "context.")

    # with self.argument_context('bake user check') as c:
    #     c.argument('user', options_list=['--user', '-u'],
    #                help='User ')
