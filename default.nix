with import (builtins.getEnv "NIXPKGS") {};

stdenv.mkDerivation {
  name = "nixos-deploy-network";

  src = ./src;

  buildInputs = [ perl makeWrapper perlPackages.XMLLibXML perlPackages.JSON ];

  installPhase = 
    ''
      mkdir -p $out/bin
      cp nixos-deploy-network.pl $out/bin/nixos-deploy-network
      chmod u+x $out/bin/nixos-deploy-network
      cp *.nix $out/bin/ # urgh

      wrapProgram $out/bin/nixos-deploy-network \
        --set PERL5LIB $PERL5LIB       
    '';
}
