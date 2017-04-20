{ config, lib, uuid, name, ... }:

with import ./lib.nix lib;
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

    cidrBlock = mkOption {
      type = types.str;
      description = "The CIDR block for the VPC subnet";
    };

    zone = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = ''
        The availability zone for the VPC subnet.
        By default AWS selects one for you.
      '';
    };

    mapPublicIpOnLaunch = mkOption {
      default = false;
      type = types.bool;
      description = ''
        Indicates whether instances launched into the subnet should be assigned
        a public IP in launch. Default is false.
      '';
    };

  } // import ./common-ec2-options.nix { inherit lib; } ;

}
