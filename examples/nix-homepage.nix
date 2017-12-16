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
        rev = "2aa65af0cf4d15109bf985f4ad2f01941100f5d8";
        sha256 = "1szmzfpxxsp38mxs2nzx5awbr8av6z11bnv23dvs57y8lyyrp0g2";
      };
      buildInputs =
        [ perl
          perlPackages.TemplateToolkit
          perlPackages.TemplatePluginJSONEscape
          perlPackages.TemplatePluginIOAll
          perlPackages.XMLSimple
          python2
          libxslt libxml2 imagemagick
          xhtml1
          nix
        ];
      preBuild =
        ''
          patchShebangs .
          echo '[]' > nixpkgs-commits.json
          echo '[]' > nixpkgs-commit-stats.json
          touch blogs.xml
          echo '[]' > blogs.json
          cp ${<nixpkgs/nixos/modules/virtualisation/ec2-amis.nix>} nixos/amis.nix
          ln -s ${nix}/share/doc/nix/manual nix/manual-raw
          ln -s ${config.system.build.manual.manual}/share/doc/nixos nixos/manual-raw
          ln -s ${(import ../release.nix {}).build.x86_64-linux}/share/doc/nixops nixops/manual-raw
          export NIX_STATE_DIR=$(pwd)/tmp
          nix-store --init
          touch nixpkgs/packages.json.gz nixos/options.json.gz
        '';
      installPhase =
        ''
          rm -rf nix/manual-raw nixos/manual-raw nixops/manual-raw
          mkdir -p $out
          cp -prvd * $out/
        '';
    };
}
