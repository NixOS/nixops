#!/usr/bin/env nix-shell
#!nix-shell ../shell.nix -i bash

exec flake8 nixops tests/unit
