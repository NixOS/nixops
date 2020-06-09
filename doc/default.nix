# FIXME: pin nixpkgs
{ nixpkgs ? <nixpkgs>
, pkgs ? import nixpkgs {}
}:

pkgs.stdenv.mkDerivation {
  name = "nixops-manual";
  src = pkgs.nix-gitignore.gitignoreSource [] ../.;
  sourceRoot = "nixops/doc";

  buildInputs = [(
    pkgs.python3.withPackages(p: [ p.sphinx ]))
    pkgs.codespell
  ];
  buildPhase = ''
    find ./ -name '*.rst' | xargs codespell

    # Workaround for https://github.com/sphinx-doc/sphinx/issues/3451
    export SOURCE_DATE_EPOCH=$(${pkgs.coreutils}/bin/date +%s)
    SPHINXOPTS=-Wn make html
  '';
  installPhase = ''
    cp -r _build/html $out
  '';
}
