{ pkgs ? import <nixpkgs> {} }:

let

  overrides = import ./overrides.nix { inherit pkgs; };

in pkgs.poetry2nix.mkPoetryApplication {
  # Once the latest poetry2nix release has reached 20.03 use projectDir instead of:
  # - src
  # - pyproject
  # - poetrylock

  src = pkgs.lib.cleanSource ./.;
  pyproject = ./pyproject.toml;
  poetrylock = ./poetry.lock;

  propagatedBuildInputs = [
    pkgs.openssh
  ];

  overrides = [
    pkgs.poetry2nix.defaultPoetryOverrides
    overrides
  ];

}
