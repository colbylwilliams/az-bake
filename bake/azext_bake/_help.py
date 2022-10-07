# coding=utf-8
# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

from knack.help_files import helps  # pylint: disable=unused-import

# ----------------
# bake
# ----------------

helps['bake'] = """
type: group
short-summary: Utilities for common or dev center tasks.
"""

helps['bake upgrade'] = """
type: command
short-summary: Update bake cli extension.
examples:
  - name: Update bake cli extension.
    text: az bake upgrade
  - name: Update bake cli extension to the latest pre-release.
    text: az bake upgrade --pre
"""

# ----------------
# bake sandbox
# ----------------

helps['bake sandbox'] = """
type: group
short-summary: Create and manage sandboxes.
"""

# helps['bake sandbox create'] = """
# type: command
# short-summary: Create a sandbox.
# examples:
#   - name: Create a sandbox.
#     text: az bake sandbox create -n mySandbox -l westus2 -p myPrefix
#   - name: Create a sandbox with a custom templates.json file.
#     text: az bake sandbox create -n mySandbox -l westus2 -p myPrefix --templates-url
# """


# ----------------
# az bake repo
# az bake validate repo
# az bake validate image
# az bake validate sandbox
# ----------------
