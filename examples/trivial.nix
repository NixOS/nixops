{
  network.name = "Trivial test network";

  machine =
    { config, pkgs, ... }:
    
    { services.httpd.enable = true;
      services.httpd.adminAddr = "e.dolstra@tudelft.nlll";

      # Serve the NixOS homepage.
      services.httpd.documentRoot =
        pkgs.stdenv.mkDerivation {
          name = "nixos.org-homepage";
          src = pkgs.fetchsvn {
            url = https://nixos.org/repos/nix/homepage/trunk;
            rev = 31592;
            sha256 = "16rdf319yzbw06bx7qryip557jnkl3z7mmsv8c7hv22hl7dph6a6";
          };
          buildInputs = [ pkgs.perlPackages.TemplateToolkit pkgs.libxslt pkgs.libxml2 pkgs.imagemagick ];
          makeFlags = "catalog=${pkgs.xhtml1}/xml/dtd/xhtml1/catalog.xml";
          installPhase =
            ''
              mkdir -p $out
              cp -prvd * $out/
              cp -prvd ${/home/eelco/Dev/hydra/src/root/static/images} $out/images
            '';
        };
    };
}
