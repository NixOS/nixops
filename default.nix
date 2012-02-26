with import <nixpkgs> {};

stdenv.mkDerivation {
  name = "charon";

  src = lib.cleanSource ./.;

  buildInputs =
    [ perl makeWrapper perlPackages.XMLLibXML perlPackages.JSON
      perlPackages.TextTable perlPackages.ListMoreUtils
      perlPackages.NetAmazonEC2 perlPackages.FileSlurp
      perlPackages.DataUUID perlPackages.SetObject
      #nixUnstable
    ];

  installPhase = 
    ''
      mkdir -p $out/bin
      cp src/charon.pl $out/bin/charon

      mkdir -p $out/share/nix/charon
      cp nix/*.nix nix/id* $out/share/nix/charon/ # urgh!

      wrapProgram $out/bin/charon \
        --set PERL5LIB $PERL5LIB \
        --prefix NIX_PATH : charon=$out/share/nix/charon
    ''; # */
}
