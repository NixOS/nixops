with import <nixpkgs> {};

pythonPackages.buildPythonPackage {
  name = "charon";
  namePrefix = "";

  src = lib.cleanSource ./.;

  doCheck = false;

  pythonPath = [ pythonPackages.prettytable pythonPackages.boto ];

  installCommand = "python setup.py install --prefix=$out";
}
