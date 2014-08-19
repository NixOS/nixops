{ config, lib, ... }:

with lib;

let

  machine = mkOptionType {
    name = "a machine";
    check = x: x._type or "" == "machine";
    merge = mergeOneOption;
  };

in

{

  options = {

    deployment.container.host = mkOption {
      type = types.either types.str machine;
      apply = x: if builtins.isString x then x else "__machine-" + x._name;
      default = "localhost";
      description = ''
        The NixOS machine on which this container is to be instantiated.
      '';
    };

  };

  config = mkIf (config.deployment.targetEnv == "container") {

    boot.isContainer = true;

    networking.useDHCP = false;

    services.openssh.enable = true;
    services.openssh.startWhenNeeded = false;
    services.openssh.extraConfig = "UseDNS no";

  };

}
