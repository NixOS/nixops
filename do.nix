{ fetchurl, python2Packages }:
python2Packages.buildPythonPackage rec {
  name = "python-digitalocean-1.10.1";
  doCheck = false;
  propagatedBuildInputs = with python2Packages; [ requests2 ];
  src = fetchurl {
    url = "mirror://pypi/p/python-digitalocean/${name}.tar.gz";
    sha256 = "12qybflfnl08acspz7rpaprmlabgrzimacbd7gm9qs5537hl3qnp";
  };
}
