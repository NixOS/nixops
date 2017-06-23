{ config, lib, uuid, name, ... }:

with import ./lib.nix lib;
with lib;

{
  options = {

    name = mkOption {
      default = "charon-${uuid}-${name}";
      type = types.str;
      description = "Name of the VPC NAT gateway.";
    };

    accessKeyId = mkOption {
      type = types.str;
      description = "The AWS Access Key ID.";
    };

    region = mkOption {
      type = types.str;
      description = "AWS region.";
    };

    allocationId = mkOption {
      type = types.either types.str (resource "elastic-ip");
      apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type + "allocation_id";
      description = ''
        The allocation ID of the elastic IP address.
      '';
    };

    subnetId = mkOption {
      type = types.either types.str (resource "vpc-subnet");
      apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type;
      description = ''
        The ID of the VPC subnet where the NAT gateway will be created
      '';
    };
  } // import ./common-ec2-options.nix { inherit lib; };
}
