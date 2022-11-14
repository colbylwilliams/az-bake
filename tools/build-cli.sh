#!/bin/bash

set -e

cdir=$(cd -P -- "$(dirname -- "$0")" && pwd -P)
tcdir=${cdir%/*}

echo "Azure CLI Build Utility"
echo ""

pushd $tcdir > /dev/null

    echo "Creating a virtual environment"
    python -m venv .venv
    echo ""

    echo "Activating virtual environment"
    source .venv/bin/activate
    echo ""

    echo "Installing Azure CLI Dev Tools (azdev)"
    pip install azdev
    echo ""

    echo "Setting up Azure CLI Dev Tools (azdev)"
    azdev setup -r $PWD -e bake
    echo ""

    echo "Running Linter on bake extension source"
    azdev linter bake
    echo ""

    echo "Running Style Checks on bake extension source"
    azdev style bake
    echo ""

    echo "Building bake extension"
    azdev extension build bake --dist-dir ./release_assets
    echo ""

    echo "Deactivating virtual environment"
    deactivate
    echo ""

popd > /dev/null

echo "Done."
echo ""
