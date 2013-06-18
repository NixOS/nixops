{ nixopsSrc ? { outPath = ./.; revCount = 0; shortRev = "abcdef"; rev = "HEAD"; }
, officialRelease ? false
}:

let

  pkgs = import <nixpkgs> { };

  version = "1.0" + (if officialRelease then "" else "pre${toString nixopsSrc.revCount}_${nixopsSrc.shortRev}");

in

rec {

  tarball = pkgs.releaseTools.sourceTarball {
    name = "nixops-tarball";
    src = nixopsSrc;
    inherit version;
    officialRelease = true; # hack
    buildInputs = [ pkgs.git ];
    postUnpack = ''
      # Clean up when building from a working tree.
      (cd $sourceRoot && (git ls-files -o | xargs -r rm -v))
    '';
    distPhase =
      ''
        substituteInPlace scripts/nixops --subst-var-by version ${version}
        substituteInPlace setup.py --subst-var-by version ${version}

        releaseName=nixops-$VERSION
        mkdir ../$releaseName
        cp -prd . ../$releaseName
        rm -rf ../$releaseName/.git
        mkdir $out/tarballs
        tar  cvfj $out/tarballs/$releaseName.tar.bz2 -C .. $releaseName
      '';
  };

  build = import ./default.nix {
    version = tarball.version;
    revision = nixopsSrc.rev;
  };

  tests.none_backend = (import ./tests/none-backend.nix {
    nixops = build;
    system = "x86_64-linux";
  }).test;

}
