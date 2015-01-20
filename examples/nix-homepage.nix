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
        rev = "9cb4cb91b4d2e4cb00310804eea5971db85ca1af";
        sha256 = "0b39slhysmld4kxb69myxri4lnc75w61bzxfq9w1r5ii40zlwkmx";
      };
      buildInputs =
        [ perl
          perlPackages.TemplateToolkit
          perlPackages.TemplatePluginJSONEscape
          perlPackages.TemplatePluginIOAll
          perlPackages.XMLSimple
          python
          libxslt libxml2 imagemagick
          xhtml1
          nix
        ];
      preBuild =
        ''
          echo '[]' > nixpkgs-commits.json
          echo '[]' > nixpkgs-commit-stats.json
          touch blogs.xml
          echo '[]' > blogs.json
          cp ${../nix/ec2-amis.nix} nixos/amis.nix
          ln -s ${nix}/share/doc/nix/manual nix/manual-raw
          ln -s ${config.system.build.manual.manual}/share/doc/nixos nixos/manual-raw
          ln -s ${(import ../release.nix {}).build.x86_64-linux}/share/doc/nixops nixops/manual-raw
          export NIX_STATE_DIR=$(pwd)/tmp
          nix-store --init
          touch nixpkgs/packages.json.gz nixos/options.json.gz
        '';
      installPhase =
        ''
          mkdir -p $out
          cp -prvd * $out/
        '';
    };
}
