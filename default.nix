{ pkgs ? import <nixpkgs> {} }:
(import ./flake-compat.nix { inherit pkgs; }).defaultNix
