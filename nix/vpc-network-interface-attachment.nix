{ config, lib, uuid, name, ... }:

with import ./lib.nix lib;
with lib;
let
  machine= mkOptionType {
    name = "EC2 machine";
    check = x: x ? ec2;
    merge = mergeOneOption;
  };
in
{
  imports = [ ./common-ec2-auth-options.nix ];

  options = {

    name = mkOption {
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the VPC network interface attachment.";
    };
    
    networkInterfaceId = mkOption {
      type = types.either types.str (resource "vpc-network-interface");
      apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type;
      description = ''
        ENI ID to attach to.
      '';
    };

    instanceId = mkOption {
      type = types.either types.str machine;
      apply = x: if builtins.isString x then x else "res-" + x._name + ".ec2." + "vm_id";
      description = ''
        ID of the instance to attach to.
      '';
    };

    deviceIndex = mkOption {
      type = types.int;
      description = ''
        The index of the device for the network interface attachment.
      '';
    };

  };

  config = {
    _type = "vpc-network-interface-attachment";
  };

}
