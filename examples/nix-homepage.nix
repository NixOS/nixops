{ config, pkgs, ... }:

{ services.httpd.enable = true;
  services.httpd.adminAddr = "eelco.dolstra@logicblox.com";

  networking.firewall.allowedTCPPorts = [ 80 ];

  # Serve the NixOS homepage.
  services.httpd.documentRoot =
    with pkgs;
    stdenv.mkDerivation {
      name = "nixos.org-homepage";
      src = fetchFromGitHub {
        owner = "NixOS";
        repo = "nixos-homepage";
        rev = "f3a5fb66968552cc21d4cbbb5137ca253af493e3";
        sha256 = "0ydllq4ir40l6icjzmsq93jvidvf0wyc8nbd10rnklrb4r0qv2vx";
      };
      buildInputs =
        [ perl
          perlPackages.TemplateToolkit
          perlPackages.TemplatePluginJSONEscape
          perlPackages.TemplatePluginIOAll
          perlPackages.XMLSimple
          libxslt libxml2 imagemagick
          xhtml1
        ];
      makeFlags = "catalog=${pkgs.xhtml1}/xml/dtd/xhtml1/catalog.xml";
      preBuild =
        ''
          echo '[]' > nixpkgs-commits.json
          echo '[]' > nixpkgs-commit-stats.json
          touch blogs.xml
          echo '[]' > blogs.json
          touch nixos/amis.nix
          cp ${config.system.build.manual.manual}/share/doc/nixos/manual.html nixos/manual/manual.html
        '';
      installPhase =
        ''
          mkdir -p $out
          cp -prvd * $out/
        '';
    };
}
