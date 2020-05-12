{
  sources ? import ./nix/sources.nix
  , pkgs ? import sources.nixpkgs { }
}:

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
    pkgs.rsync  # Included by default on NixOS
    pkgs.codespell
    pkgs.niv
  ];

  shellHook = ''
    export PATH=${builtins.toString ./scripts}:$PATH
  '';

}
