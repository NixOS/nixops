{ config, pkgs, ... }:

{ services.httpd.enable = true;
  services.httpd.adminAddr = "eelco.dolstra@logicblox.com";

  # Serve the NixOS homepage.
  services.httpd.documentRoot =
    pkgs.stdenv.mkDerivation {
      name = "nixos.org-homepage";
      src = pkgs.fetchsvn {
        url = https://nixos.org/repos/nix/homepage/trunk;
        rev = 32142;
        sha256 = "0xzlvardwy3dsa12xxmin61hgh19hai55ird4xk12sn5x68v7anx";
      };
      buildInputs = [ pkgs.perlPackages.TemplateToolkit pkgs.libxslt pkgs.libxml2 pkgs.imagemagick ];
      makeFlags = "catalog=${pkgs.xhtml1}/xml/dtd/xhtml1/catalog.xml";
      installPhase =
        ''
          mkdir -p $out
          cp -prvd * $out/
        '';
    };
}
