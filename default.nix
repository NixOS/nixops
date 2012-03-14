with import <nixpkgs> {};

pythonPackages.buildPythonPackage {
  name = "charon";

  src = lib.cleanSource ./.;

  doCheck = false;

  pythonPath = [ pythonPackages.prettytable ];

  installCommand = "python setup.py install --prefix=$out";
}
