# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------


from ._validators import (builder_validator, process_bake_repo_build_namespace, process_bake_repo_validate_namespace,
                          process_sandbox_create_namespace)


def load_command_table(self, _):  # pylint: disable=too-many-statements

    with self.command_group('bake', is_preview=True):
        pass

    with self.command_group('bake') as g:
        # g.custom_command('test', 'bake_tests')
        g.custom_command('version', 'bake_version')
        g.custom_command('upgrade', 'bake_upgrade')
        # g.custom_command('image', 'bake_image', validator=process_bake_image_namespace)

    with self.command_group('bake sandbox') as g:
        g.custom_command('create', 'bake_sandbox_create', validator=process_sandbox_create_namespace)
        g.custom_command('validate', 'bake_sandbox_validate')

    with self.command_group('bake repo') as g:
        g.custom_command('build', 'bake_repo_build', validator=process_bake_repo_build_namespace)
        g.custom_command('validate', 'bake_repo_validate', validator=process_bake_repo_validate_namespace)
        g.custom_command('setup', 'bake_repo_setup')

    with self.command_group('bake yaml') as g:
        g.custom_command('export', 'bake_yaml_export')
        # g.custom_command('validate', 'bake_yaml_validate')

    with self.command_group('bake validate') as g:
        # g.custom_command('image', 'bake_validate_image')
        g.custom_command('repo', 'bake_repo_validate', validator=process_bake_repo_validate_namespace)
        g.custom_command('sandbox', 'bake_sandbox_validate')
        # g.custom_command('yaml', 'bake_yaml_validate')

    with self.command_group('bake image') as g:
        g.custom_command('create', 'bake_image_create')
        g.custom_command('logs', 'bake_image_logs')

    with self.command_group('bake _builder') as g:
        g.custom_command('build', 'bake_builder_build', validator=builder_validator)
