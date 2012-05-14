with import <nixpkgs> {};

pythonPackages.buildPythonPackage {
  name = "charon";
  namePrefix = "";

  src = ./.;

  buildInputs = [ git ];

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
}
