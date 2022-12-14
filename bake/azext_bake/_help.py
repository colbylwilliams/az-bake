# coding=utf-8
# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

from knack.help_files import helps  # pylint: disable=unused-import

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
    text: |
      az bake sandbox create -l eastus --name mySandbox \\
        --gallery myGallery --principal CI_SP_ID
  - name: Create a sandbox with an existing resource group.
    text: |
      az bake sandbox create -l eastus -g mySandbox --name my-sandbox \\
        --gallery myGallery --principal CI_SP_ID
"""

helps['bake sandbox validate'] = """
type: command
short-summary: Validate a sandbox.
examples:
  - name: Validate a sandbox.
    text: az bake sandbox validate --sandbox mySandbox
  - name: Validate a sandbox and ensure the correct permissions on a gallery.
    text: az bake sandbox validate --sandbox mySandbox --gallery myGallery
"""


# ----------------
# bake repo
# ----------------

helps['bake repo'] = """
type: group
short-summary: Configure, validate, and bake images in a repo.
"""

helps['bake repo build'] = """
type: command
short-summary: Bake images defined in a repo (usually run in CI).
examples:
  - name: Build all the images in a repo.
    text: az bake repo build --repo .
"""

helps['bake repo setup'] = """
type: command
short-summary: Setup a repo for baking.
examples:
  - name: Setup a repo for baking.
    text: az bake repo setup --sandbox mySandbox --gallery myGallery
"""

helps['bake repo validate'] = """
type: command
short-summary: Validate a repo.
examples:
  - name: Validate a repo.
    text: az bake repo validate --repo .
"""


# ----------------
# bake image
# ----------------

helps['bake image'] = """
type: group
short-summary: Create and manage images.
"""

helps['bake image create'] = """
type: command
short-summary: Create an image.
examples:
  - name: Create an image.yml file.
    text: az bake image create --name myImage
"""

helps['bake image logs'] = """
type: command
short-summary: Get the logs for an image build.
examples:
  - name: Get the logs for an image.
    text: az bake image logs --sandbox mySandbox --name myImage
"""

helps['bake image rebuild'] = """
type: command
short-summary: Rebuild an image that failed.
examples:
  - name: Rebuild an image that failed.
    text: az bake image rebuild --sandbox mySandbox --name myImage
"""

helps['bake image bump'] = """
type: command
short-summary: Bump the version number of images.
examples:
  - name: Bump the patch version of all images.
    text: az bake image bump
  - name: Bump the minor version of all images.
    text: az bake image bump --minor
  - name: Bump the major version of specific images.
    text: az bake image bump --major --images myImage1 MyImage2
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
    text: az bake yaml export --sandbox mySandbox --gallery myGallery --outdir ./myDir
  - name: Export a bake.yaml file to a specific file.
    text: az bake yaml export --sandbox mySandbox --gallery myGallery --outfile ./myDir/myFile.yaml
  - name: Print the bake.yaml file output to the console.
    text: az bake yaml export --sandbox mySandbox --gallery myGallery --stdout
"""


# ----------------
# bake _builder
# ----------------

helps['bake _builder'] = """
type: group
short-summary: Should not be used directly (used by packer image).
"""

helps['bake _builder build'] = """
type: command
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
short-summary: Validate a sandbox. This is an alias for 'az bake sandbox validate'.
examples:
  - name: Validate a sandbox.
    text: az bake validate sandbox --sandbox mySandbox --gallery /My/Gallery/Resource/ID
"""

helps['bake validate repo'] = """
type: command
short-summary: Validate a repo. This is an alias for 'az bake repo validate'.
examples:
  - name: Validate a repo.
    text: az bake validate repo --repo .
"""


# ----------------
# bake version
# bake upgrade
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
