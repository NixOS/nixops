{ config, lib, ... }:

with lib;

{
  config = mkIf config.boot.isContainer {
    networking.useDHCP = false;
    services.openssh.enable = true;
    services.openssh.startWhenNeeded = false;
    services.openssh.extraConfig = "UseDNS no";
  };
}
