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
# bake foo
# ----------------
