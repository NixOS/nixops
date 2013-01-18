{ version ? "0", revision ? "local" }:

with import <nixpkgs> {};

pythonPackages.buildPythonPackage rec {
  name = "charon-${version}";
  namePrefix = "";

  src = ./.;

  buildInputs = [ git libxslt docbook_xsl ];

  propagatedBuildInputs =
    [ pythonPackages.prettytable
      pythonPackages.boto
      pythonPackages.sqlite3
    ];

  # XXX: needed until nix stops to preserve the epoch 0 timestamp when
  # copying source from store to tmp build directory or python zip
  # knows how to handle epoch 0
  preConfigure = ''
    find . |xargs touch
  '';

  postUnpack = ''
    # Clean up when building from a working tree.
    (cd $sourceRoot && (git ls-files -o | xargs -r rm -v))
  '';

  doCheck = false;

  postInstall =
    ''
      cp ${import ./doc/manual { inherit revision; }} doc/manual/options-db.xml

      make -C doc/manual install docbookxsl=${docbook5_xsl}/xml/xsl/docbook \
        docdir=$out/share/doc/charon mandir=$out/share/man

      mkdir -p $out/share/nix
      cp -av nix/* $out/share/nix

      mkdir -p $out/nix-support
      echo "nix-build none $out" >> $out/nix-support/hydra-build-products
      echo "doc manual $out/share/doc/charon manual.html" >> $out/nix-support/hydra-build-products
    '';
}
