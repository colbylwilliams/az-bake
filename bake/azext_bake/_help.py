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

helps['bake sandbox create'] = """
type: command
short-summary: Create a sandbox.
examples:
  - name: Create a sandbox.
    text: az bake sandbox create -sb mySandbox -n myPrefix
"""

helps['bake sandbox validate'] = """
type: command
short-summary: Validate a sandbox.
examples:
  - name: Validate a sandbox.
    text: az bake sandbox validate -sb mySandbox
"""

helps['bake repo'] = """
type: group
short-summary: Configure, validate, and bake images in a repo.
"""

helps['bake repo'] = """
type: command
short-summary: Bake all images in a repo.
examples:
  - name: Build all the images in a repo.
    text: az bake repo -r .
"""

helps['bake repo validate'] = """
type: command
short-summary: Validate a repo.
examples:
  - name: Validate a repo.
    text: az bake repo validate -r .
"""


helps['bake yaml'] = """
type: group
short-summary: Export and validate bake.yaml files.
"""

helps['bake yaml export'] = """
type: command
short-summary: Export a bake.yaml file.
examples:
  - name: Export a bake.yaml file.
    text: az bake yaml export -sb MySandbox -g /My/Gallery/Resource/ID
"""

helps['bake yaml validate'] = """
type: command
short-summary: Validate a bake.yaml file.
examples:
  - name: Validate a bake.yaml file.
    text: az bake yaml validate -f ./bake.yaml
"""

helps['bake _builder'] = """
type: group
short-summary: Used by the builder container to execute packer.
"""

# ----------------
# az bake repo
# az bake validate repo
# az bake validate image
# az bake validate sandbox
# ----------------
