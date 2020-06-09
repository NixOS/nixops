{
  description = "NixOps: a tool for deploying to [NixOS](https://nixos.org) machines in a network or the cloud";

  inputs.nixpkgs.url = github:NixOS/nixpkgs/nixpkgs-unstable;

  outputs = { self, nixpkgs }: let
    pkgs = import nixpkgs { system = "x86_64-linux"; };
  in {
    defaultPackage.x86_64-linux = let
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
  };
}
