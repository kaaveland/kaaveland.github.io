#!/usr/bin/env bash

set -e -u -f -o pipefail

mkdir -p themes

echo "Adding PaperMod theme as a submodule"

git submodule add --force --depth=1 https://github.com/adityatelange/hugo-PaperMod.git themes/PaperMod || true
git submodule update --init --recursive
git submodule set-branch --branch v8.0 themes/PaperMod
