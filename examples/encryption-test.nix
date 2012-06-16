{
  network.description = "Encryption test";

  machine1 =
    { config, pkgs, ... }:
    { deployment.targetEnv = "virtualbox";
      deployment.encryptedLinksTo = [ "machine2" "machine3" ];
    };

  machine2 =
    { config, pkgs, ... }:
    { deployment.targetEnv = "virtualbox";
      deployment.encryptedLinksTo = [ "machine1" "machine3" ];
      
      services.httpd.enable = true;
      services.httpd.adminAddr = "e.dolstra@tudelft.nl";
      services.httpd.documentRoot = "/tmp";
    };

  machine3 =
    { config, pkgs, ... }:
    { deployment.targetEnv = "virtualbox";
      deployment.encryptedLinksTo = [ "machine1" "machine2" ];
    };
}
