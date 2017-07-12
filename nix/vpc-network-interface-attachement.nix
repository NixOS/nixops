{ config, lib, uuid, name, ... }:

with import ./lib.nix lib;
with lib;
{
  options = {

    name = mkOption {
      default = "charon-${uuid}-${name}";
      type = types.str;
      description = "Name of the VPC network interface attachement.";
    };
    
    accessKeyId = mkOption {
      type = types.str;
      description = "The AWS Access Key ID.";
    };

    region = mkOption {
      type = types.str;
      description = "AWS region.";
    };

    networkInterfaceId = mkOption {
      type = types.either types.str (resource "vpc-network-interface");
      description = ''
        ENI ID to attach to.
      '';
    };

    instanceId = mkOption {
      type = types.either types.str (resource "ec2");
      apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type;
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
    _type = "vpc-network-interface-attachement";
  };

}
