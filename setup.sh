#!/usr/bin/env bash

set -e -u -f -o pipefail

mkdir -p themes

if ! [[ -d 'themes/PaperMod' ]]; then
    git submodule add --force --depth=1 https://github.com/adityatelange/hugo-PaperMod.git themes/PaperMod
    git submodule update --init --recursive
    git submodule set-branch --branch v7.0 themes/PaperMod
fi
