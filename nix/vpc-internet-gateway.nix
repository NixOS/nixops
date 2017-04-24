{ config, lib, uuid, name, ... }:

with lib;

{
  options = {

    name = mkOption {
      default = "charon-${uuid}-${name}";
      type = types.str;
      description = "Name of the subnet VPC.";
    };
    
    accessKeyId = mkOption {
      type = types.str;
      description = "The AWS Access Key ID.";
    };

    region = mkOption {
      type = types.str;
      description = "AWS region.";
    };

    vpcId = mkOption {
      type = types.either types.str (resource "vpc");
      apply = x: if builtins.isString x then x else "res-" + x._name;
      description = ''
        The ID of the VPC where the subnet will be created
      '';
    };
  } // import ./common-ec2-options.nix { inherit lib; };
}
