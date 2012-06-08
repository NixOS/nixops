{ version ? "0", revision ? "local" }:

with import <nixpkgs> {};

pythonPackages.buildPythonPackage {
  name = "charon-${version}";
  namePrefix = "";

  src = ./.;

  buildInputs = [ git libxslt docbook_xsl ];

  postUnpack = ''
    # Clean up when building from a working tree.
    (cd $sourceRoot && (git ls-files -o | xargs -r rm -v))
  '';

  doCheck = false;

  pythonPath =
    [ pythonPackages.prettytable
      pythonPackages.boto
    ];

  installCommand = "python setup.py install --prefix=$out";

  postInstall =
    ''
      cp ${import ./doc/manual { inherit revision; }} doc/manual/options-db.xml

      make -C doc/manual install docbookxsl=${docbook5_xsl}/xml/xsl/docbook \
        docdir=$out/share/doc/charon mandir=$out/share/man

      mkdir -p $out/nix-support
      echo "nix-build none $out" >> $out/nix-support/hydra-build-products
      echo "doc manual $out/share/doc/charon manual.html" >> $out/nix-support/hydra-build-products
    '';
}
