{ charonSrc ? { outPath = ./.; revCount = 1234; shortRev = "abcdef"; }
, officialRelease ? false
}:

let pkgs = import <nixpkgs> { }; in

rec {

  tarball = pkgs.releaseTools.sourceTarball {
    name = "charon-tarball";
    version = "0.1";
    versionSuffix = if officialRelease then "" else "pre${toString charonSrc.revCount}_${charonSrc.shortRev}";
    src = charonSrc;
    inherit officialRelease;
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

}
