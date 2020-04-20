#!/usr/bin/env nix-shell
#!nix-shell ../shell.nix -i bash

./coverage-tests.py -a '!libvirtd,!gce,!ec2,!azure' -v
