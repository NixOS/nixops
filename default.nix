{ version ? "0", revision ? "local" }:

with import <nixpkgs> {};

pythonPackages.buildPythonPackage rec {
  name = "nixops-${version}";
  namePrefix = "";

  src = ./.;

  buildInputs = [ git libxslt docbook_xsl pythonPackages.nose pythonPackages.coverage ];

  propagatedBuildInputs =
    [ pythonPackages.prettytable
      pythonPackages.boto
      pythonPackages.sqlite3
    ];

  # For "nix-build --run-env".
  postHook = ''
    export PYTHONPATH=$(pwd):$PYTHONPATH
    export PATH=$(pwd)/scripts:$PATH
  '';

  # XXX: needed until nix stops to preserve the epoch 0 timestamp when
  # copying source from store to tmp build directory or python zip
  # knows how to handle epoch 0
  preConfigure = ''
    find . | xargs touch

    substituteInPlace scripts/nixops --subst-var-by version ${version}
    substituteInPlace setup.py --subst-var-by version ${version}
  '';

  postUnpack = ''
    # Clean up when building from a working tree.
    (cd $sourceRoot && (git ls-files -o | xargs -r rm -v))
  '';

  doCheck = false;

  postInstall =
    ''
      # Backward compatibility symlink.
      ln -s nixops $out/bin/charon

      cp ${import ./doc/manual { inherit revision; }} doc/manual/machine-options.xml
      ${stdenv.lib.concatMapStrings (fn: ''
        cp ${import ./doc/manual/resource.nix { inherit revision; module = ./nix + ("/" + fn + ".nix"); }} doc/manual/${fn}-options.xml
      '') [ "sqs-queue" "ec2-keypair" "s3-bucket" "iam-role" ]}

      make -C doc/manual install docbookxsl=${docbook5_xsl}/xml/xsl/docbook \
        docdir=$out/share/doc/nixops mandir=$out/share/man

      mkdir -p $out/share/nix/nixops
      cp -av nix/* $out/share/nix/nixops

      mkdir -p $out/nix-support
      echo "nix-build none $out" >> $out/nix-support/hydra-build-products
      echo "doc manual $out/share/doc/nixops manual.html" >> $out/nix-support/hydra-build-products
    '';

  meta.description = "Nix package for ${stdenv.system}";
}
