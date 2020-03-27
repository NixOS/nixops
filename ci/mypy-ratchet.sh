#!/usr/bin/env bash

set -eu

cd "${0%/*}/.."

scratch=$(mktemp -d -t tmp.XXXXXXXXXX)
function finish {
    rm -rf "$scratch"
}
# trap finish EXIT

cp ci/run-ratchet.sh $scratch/

head=$(git rev-parse HEAD)
base=origin/${GITHUB_BASE_REF:-master}

git fetch origin

echo "Checking base branch at %s, then PR at %s...\n" "$base" "$head"

git checkout "$base"
nix-shell shell.nix --run "$scratch/run-ratchet.sh $scratch base"

git checkout "$head"
nix-shell shell.nix --run "$scratch/run-ratchet.sh $scratch head"

diff --ignore-all-space -u100 -r  "$scratch/base/" "$scratch/head/" || true

nix-shell shell.nix --run "mypy ./ci/ratchet.py"
nix-shell shell.nix --run "python3 ./ci/ratchet.py $scratch"
