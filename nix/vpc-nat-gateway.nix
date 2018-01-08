{ config, lib, uuid, name, ... }:

with import ./lib.nix lib;
with lib;

{
  imports = [ ./common-ec2-auth-options.nix ];

  options = {

    name = mkOption {
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the VPC NAT gateway.";
    };

    allocationId = mkOption {
      type = types.either types.str (resource "elastic-ip");
      apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type + ".allocation_id";
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
  };

  config._type = "vpc-nat-gateway";
}
