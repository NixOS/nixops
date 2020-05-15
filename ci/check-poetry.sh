#!/usr/bin/env nix-shell
#!nix-shell ../shell.nix -i bash

set -eu

set -x
poetry export --dev -f requirements.txt > doc/requirements.txt
git diff --exit-code poetry.lock doc/requirements.txt
