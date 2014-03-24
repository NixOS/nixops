{ config, pkgs, ... }:

with pkgs.lib;

{

  options = {

    deployment.container.host = mkOption {
      type = types.string;
      default = "localhost";
      description = ''
        The NixOS machine on which this container is to be instantiated.
      '';
    };

  };

  config = mkIf (config.deployment.targetEnv == "container") {

    boot.isContainer = true;
    services.openssh.enable = true;
    services.openssh.extraConfig = "UseDNS no";

  };

}
