{ charonSrc ? { outPath = ./.; revCount = 0; shortRev = "abcdef"; }
, officialRelease ? false
}:

let

  pkgs = import <nixpkgs> { };

  version = "0.1";
  versionSuffix = if officialRelease then "" else "pre${toString charonSrc.revCount}_${charonSrc.shortRev}";
  
in

rec {

  tarball = pkgs.releaseTools.sourceTarball {
    name = "charon-tarball";
    src = charonSrc;
    inherit version versionSuffix officialRelease;
    buildInputs = [ pkgs.git ];
    postUnpack = ''
      # Clean up when building from a working tree.
      (cd $sourceRoot && (git ls-files -o | xargs -r rm -v))
    '';
    distPhase =
      ''
        releaseName=charon-$VERSION$VERSION_SUFFIX
        mkdir ../$releaseName
        cp -prd . ../$releaseName
        rm -rf ../$releaseName/.git
        mkdir $out/tarballs
        tar  cvfj $out/tarballs/$releaseName.tar.bz2 -C .. $releaseName
      '';
  };

  build = import ./default.nix {
    version = tarball.version;
  };

}
