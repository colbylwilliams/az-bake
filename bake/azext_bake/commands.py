# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

# from ._transformers import transform_rg_table


def load_command_table(self, _):  # pylint: disable=too-many-statements

    with self.command_group('bake', is_preview=True):
        pass

    with self.command_group('bake') as g:
        g.custom_command('upgrade', 'bake_upgrade')
        # g.custom_command('test', 'bake_test')

    # with self.command_group('bake user') as g:
    #     g.custom_command('check', 'bake_user_check')
