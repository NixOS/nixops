{

  webserver = 
    { config, pkgs, ... }:

    with pkgs.lib;

    {
      services.httpd.enable = true;
      services.httpd.adminAddr = "e.dolstra@tudelft.nl";
      services.httpd.extraSubservices = singleton
        { serviceType = "mediawiki";
          siteName = "Example Wiki";
        };
        
      services.postgresql.enable = true;
    };

}
