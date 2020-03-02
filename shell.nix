{ pkgs ? import <nixpkgs> {} }:

let

  overrides = import ./overrides.nix { inherit pkgs; };

in pkgs.mkShell {

  buildInputs = [
    (pkgs.poetry2nix.mkPoetryEnv {
      projectDir = ./.;
      overrides = pkgs.poetry2nix.overrides.withDefaults(overrides);
    })
    pkgs.openssh
    pkgs.poetry
  ];

  shellHook = ''
    export PATH=${builtins.toString ./scripts}:$PATH
  '';

}
