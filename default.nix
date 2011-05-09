with import (builtins.getEnv "NIXPKGS") {};

stdenv.mkDerivation {
  name = "nixos-deploy-network";

  src = lib.cleanSource ./src;

  buildInputs =
    [ perl makeWrapper perlPackages.XMLLibXML perlPackages.JSON
      perlPackages.TextTable perlPackages.ListMoreUtils
    ];

  installPhase = 
    ''
      mkdir -p $out/bin
      cp nixos-deploy-network.pl $out/bin/nixos-deploy-network
      cp *.nix $out/bin/ # urgh

      wrapProgram $out/bin/nixos-deploy-network \
        --set PERL5LIB $PERL5LIB
    '';
}
