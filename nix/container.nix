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

    deployment.container = {
      
      host = mkOption {
        type = types.either types.str machine;
        apply = x: if builtins.isString x then x else "__machine-" + x._name;
        default = "localhost";
        description = ''
          The NixOS machine on which this container is to be instantiated.
        '';
      };
      
      forwardPorts = mkOption {
        type = types.listOf (types.submodule {
          options = {
            protocol = mkOption {
              type = types.str;
              default = "tcp";
              description = "The protocol specifier for port forwarding between host and container";
            };
            hostPort = mkOption {
              type = types.int;
              description = "Source port of the external interface of host";
            };
            containerPort = mkOption {
              type = types.nullOr types.int;
              default = null;
              description = "Target port of container";
            };
          };
        });
        default = [];
        example = [ { protocol = "tcp"; hostPort = 8080; containerPort = 80; } ];
        description = ''
          List of forwarded ports from host to container. Each forwarded port
          is specified by protocol, hostPort and containerPort. By default,
          protocol is tcp and hostPort and containerPort are assumed to be
          the same if containerPort is not explicitly given.
        '';
      };
    };
  };

  config = mkIf (config.deployment.targetEnv == "container") {

    boot.isContainer = true;

  };

}
