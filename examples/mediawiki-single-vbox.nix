# To create and deploy:
#     nixops create mediawiki-single.nix mediawiki-single-vbox.nix -d mwsingle
#     nixops deploy -d mwsingle
# 
# Mediawiki will then be available at `http://<ip-address>/wiki`.
{
  webserver =
    { config, pkgs, ... }:
    { deployment.targetEnv = "virtualbox";
      deployment.virtualbox.memorySize = 1024;  # megabytes
    };
}
