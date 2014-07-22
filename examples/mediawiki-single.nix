{
  network.description = "Mediawiki on one server";

  webserver = 
    { config, pkgs, ... }:

    with pkgs.lib;

    {
      # Webserver
      services.httpd = {
        enable = true;
        adminAddr = "admin@example.com";
        extraSubservices = singleton
          { serviceType = "mediawiki";
            siteName = "Example Wiki";
            logo = "http://nixos.org/logo/nix-wiki.png";
          };
      };

      # Database
      services.postgresql = {
        enable = true;
        package = pkgs.postgresql;
        authentication = ''
          local mediawiki all ident map=mwusers
          local all all ident
        '';
        identMap = ''
          mwusers root   mediawiki
          mwusers wwwrun mediawiki
        '';
      };

      # Firewall
      networking.firewall.allowedTCPPorts = [ 80 ];
    };
}
