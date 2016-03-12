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

  imports = [ ./container-base.nix ];

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

    nixpkgs.system = mkIf (! any (platform: platform == builtins.currentSystem) platforms.linux) (mkOverride 999 "x86_64-linux");
  };

}
