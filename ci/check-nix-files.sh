#!/usr/bin/env bash

find . -name "*.nix" -exec nix-instantiate --parse --quiet {} >/dev/null +
