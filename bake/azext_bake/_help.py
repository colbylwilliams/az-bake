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

helps['bake version'] = """
type: command
short-summary: Show the version of the bake extension.
"""

helps['bake upgrade'] = """
type: command
short-summary: Update bake cli extension.
examples:
  - name: Update bake cli extension to the latest stable release.
    text: az bake upgrade
  - name: Update bake cli extension to the latest pre-release.
    text: az bake upgrade --pre
  - name: Update bake cli extension a specific version.
    text: az bake upgrade --version 0.1.0
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
  - name: Create a sandbox and ensure the correct permisinos on a gallery.
    text: az bake sandbox create -sb mySandbox -n myPrefix -r myGallery
"""

helps['bake sandbox validate'] = """
type: command
short-summary: Validate a sandbox.
examples:
  - name: Validate a sandbox.
    text: az bake sandbox validate -sb mySandbox
  - name: Validate a sandbox and ensure the correct permisinos on a gallery.
    text: az bake sandbox validate -sb mySandbox -r myGallery
"""

# ----------------
# bake repo
# ----------------


helps['bake repo'] = """
type: group
short-summary: Configure, validate, and bake images in a repo.
"""

helps['bake repo'] = """
type: command
short-summary: Bake images defined in a repo.
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

# ----------------
# bake yaml
# ----------------


helps['bake yaml'] = """
type: group
short-summary: Export and validate bake.yaml files.
"""

helps['bake yaml export'] = """
type: command
short-summary: Export a bake.yaml file.
examples:
  - name: Export a bake.yaml file to a directory.
    text: az bake yaml export -sb MySandbox -r myGallery --outdir ./myDir
  - name: Export a bake.yaml file to a specific file.
    text: az bake yaml export -sb MySandbox -r myGallery --outfile ./myDir/myFile.yaml
  - name: Print the bake.yaml file output to the console.
    text: az bake yaml export -sb MySandbox -r myGallery --stdout
"""

helps['bake yaml validate'] = """
type: command
short-summary: Validate a bake.yaml file.
examples:
  - name: Validate a bake.yaml file.
    text: az bake yaml validate -f ./bake.yaml
"""

# ----------------
# bake _builder
# ----------------

helps['bake _builder'] = """
type: group
short-summary: Should not be used directly (used by packer image).
"""


# ----------------
# bake validate
# ----------------

helps['bake validate'] = """
type: group
short-summary: Validate a sandbox, repo, or image.
"""

helps['bake validate sandbox'] = """
type: command
short-summary: Validate a sandbox. This is the same as 'az bake sandbox validate'.
examples:
  - name: Validate a sandbox.
    text: az bake validate sandbox -sb mySandbox --gallery /My/Gallery/Resource/ID
"""

helps['bake validate repo'] = """
type: command
short-summary: Validate a repo. This is the same as running 'az bake repo validate'.
examples:
  - name: Validate a repo.
    text: az bake validate repo -r .
"""

helps['bake validate yaml'] = """
type: command
short-summary: Validate a bake.yaml file. This is the same as running 'az bake yaml validate'.
examples:
  - name: Validate a bake.yaml file.
    text: az bake validate yaml -f ./bake.yaml
"""


# gh secret set AZURE_TENANT_ID -R colbylwilliams/az-bake-tests -b
