#!/usr/bin/env nix-shell
#!nix-shell -i bash ../shell.nix

set -eu

scratch=$(mktemp -d -t tmp.XXXXXXXXXX)
function finish {
    rm -rf "$scratch"
}
trap finish EXIT

head=$(git rev-parse HEAD)
base=origin/${GITHUB_BASE_REF:-master}

git fetch origin

echo "Checking base branch at %s, then PR at %s...\n" "$base" "$head"

git checkout "$base"
mypy \
    --any-exprs-report "$scratch/base" \
    --linecount-report "$scratch/base" \
    --lineprecision-report "$scratch/base" \
    --txt-report "$scratch/base" \
    nixops

git checkout "$head"
mypy \
    --any-exprs-report "$scratch/head" \
    --linecount-report "$scratch/head" \
    --lineprecision-report "$scratch/head" \
    --txt-report "$scratch/head" \
    nixops

diff --ignore-all-space -u100 -r  "$scratch/base/" "$scratch/head/" || true

mypy ./ci/ratchet.py
python3 ./ci/ratchet.py "$scratch"
