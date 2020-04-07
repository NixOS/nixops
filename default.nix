{ nixpkgs ? <nixpkgs>
, pkgs ? import nixpkgs {}
}:

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
    cp ${(import ./doc/manual { revision = "1.8"; inherit nixpkgs; }).optionsDocBook} doc/manual/machine-options.xml
    make -C doc/manual install docdir=$out/share/doc/nixops mandir=$out/share/man
  '';

}
