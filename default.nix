{ pkgs ? import <nixpkgs> {} }:

let

  overrides = import ./overrides.nix { inherit pkgs; };

in pkgs.poetry2nix.mkPoetryApplication {
  projectDir = ./.;

  propagatedBuildInputs = [
    pkgs.openssh
  ];

  overrides = pkgs.poetry2nix.overrides.withDefaults(overrides);

}
