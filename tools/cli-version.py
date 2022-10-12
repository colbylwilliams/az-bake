# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

import os
from pathlib import Path
from re import search

path_root = Path(__file__).resolve().parent.parent
path_bake = path_root / 'bake'

version = None

with open(path_bake / 'setup.py', 'r') as f:
    for line in f:
        if line.startswith('VERSION'):
            txt = str(line).rstrip()
            match = search(r'VERSION = [\'\"](.*)[\'\"]$', txt)
            if match:
                version = match.group(1)

if version:
    github_output = os.environ.get('GITHUB_OUTPUT', None)
    if github_output:
        with open(github_output, 'a+') as f:
            f.write(f'version={version}\n')
