with import <nixpkgs> {};

pythonPackages.buildPythonPackage {
  name = "charon";

  src = lib.cleanSource ./.;

  doCheck = false;

  installCommand = "python setup.py install --prefix=$out";
}
