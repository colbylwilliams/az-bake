# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

# from ._transformers import transform_rg_table
from ._validators import process_sandbox_create_namespace


def load_command_table(self, _):  # pylint: disable=too-many-statements

    with self.command_group('bake', is_preview=True):
        pass

    with self.command_group('bake') as g:
        g.custom_command('upgrade', 'bake_upgrade')
        # g.custom_command('test', 'bake_test')

    with self.command_group('bake sandbox') as g:
        g.custom_command('create', 'bake_sandbox_create', validator=process_sandbox_create_namespace)
        g.custom_command('validate', 'bake_sandbox_validate')
