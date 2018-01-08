{ config, lib, uuid, name, ... }:

with import ./lib.nix lib;
with lib;
{
  imports = [ ./common-ec2-auth-options.nix ];

  options = {
    name = mkOption {
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the VPC route table association.";
    };
    
    subnetId = mkOption {
      type = types.either types.str (resource "vpc-subnet");
      apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type;
      description = ''
        The ID of the VPC subnet where the route table will be associated
      '';
    };

    routeTableId = mkOption {
      type = types.either types.str (resource "vpc-route-table");
      apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type;
      description = ''
        The ID of the VPC route table
      '';
    };
  };

  config._type = "vpc-route-table-association";
}
