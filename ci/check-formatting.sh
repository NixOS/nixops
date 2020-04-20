#!/usr/bin/env nix-shell
#!nix-shell ../shell.nix -i bash

black . --check --diff
