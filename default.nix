with import <nixpkgs> {};

stdenv.mkDerivation {
  name = "charon";

  src = lib.cleanSource ./src;

  buildInputs =
    [ perl makeWrapper perlPackages.XMLLibXML perlPackages.JSON
      perlPackages.TextTable perlPackages.ListMoreUtils
      perlPackages.NetAmazonEC2
    ];

  installPhase = 
    ''
      mkdir -p $out/bin
      cp charon.pl $out/bin/charon
      cp *.nix $out/bin/ # urgh!

      wrapProgram $out/bin/charon \
        --set PERL5LIB $PERL5LIB
    '';
}
