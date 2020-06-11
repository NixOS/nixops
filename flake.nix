{
  description = "NixOps: a tool for deploying to [NixOS](https://nixos.org) machines in a network or the cloud";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  inputs.utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, utils }: utils.lib.eachDefaultSystem (system: let
    pkgs = import nixpkgs { inherit system; };
  in {
    devShell = pkgs.mkShell {
      buildInputs = [
        (pkgs.poetry2nix.mkPoetryEnv {
          projectDir = ./.;
        })
        pkgs.openssh
        pkgs.poetry
        pkgs.rsync  # Included by default on NixOS
        pkgs.codespell
        pkgs.nixFlakes
      ];

      shellHook = ''
        export PATH=${builtins.toString ./scripts}:$PATH
      '';
    };

    defaultPackage = let
      overrides = import ./overrides.nix { inherit pkgs; };

    in pkgs.poetry2nix.mkPoetryApplication {
      projectDir = ./.;

      propagatedBuildInputs = [
        pkgs.openssh
        pkgs.rsync
      ];

      nativeBuildInputs = [
        pkgs.docbook5_xsl
        pkgs.libxslt
      ];

      overrides = [
        pkgs.poetry2nix.defaultPoetryOverrides
        overrides
      ];

      # TODO: Manual build should be included via pyproject.toml
      postInstall = ''
        cp ${(import ./doc/manual { revision = "1.8"; inherit nixpkgs; system = "x86_64-linux"; }).optionsDocBook} doc/manual/machine-options.xml

        make -C doc/manual install docdir=$out/share/doc/nixops mandir=$out/share/man
      '';
    };
  });
}
