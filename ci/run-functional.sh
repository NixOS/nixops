#!/usr/bin/env nix-shell
#!nix-shell ../shell.nix -i bash
set -eu

# We rely on commits not in 20.03 for container testing
export NIX_PATH=nixpkgs=https://github.com/NixOS/nixpkgs-channels/archive/nixos-unstable.tar.gz

exec python tests.py tests/functional
