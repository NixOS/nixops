#!/usr/bin/env nix-shell
#!nix-shell ../shell.nix -i bash
set -eu

# Check if we're in github actions
echo "Github Workflow: "$GITHUB_WORKFLOW

ln -s $(which docker) scripts/podman

# We rely on commits not in 20.03 for container testing
export NIX_PATH=nixpkgs=https://github.com/NixOS/nixpkgs-channels/archive/nixos-unstable.tar.gz

exec python tests.py tests/functional
