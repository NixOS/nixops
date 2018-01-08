{ config, lib, uuid, name, ... }:

with import ./lib.nix lib;
with lib;

{
  imports = [ ./common-ec2-auth-options.nix ];

  options = {

    name = mkOption {
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the VPC endpoint.";
    };
    
    vpcId = mkOption {
      type = types.either types.str (resource "vpc");
      apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type;
      description = ''
        The ID of the VPC where the endpoint will be created.
      '';
    };

    policy = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = ''
        A policy to attach to the endpoint that controls access to the service.
      '';
    };

    routeTableIds = mkOption {
      default = [];
      type = types.listOf (types.either types.str (resource "vpc-route-table"));
      apply = map (x: if builtins.isString x then x else "res-" + x._name + "." + x._type + "." + "routeTableId");
      description = ''
        One or more route table IDs.
      '';
    };

    serviceName = mkOption {
      type = types.str;
      description = ''
        The AWS service name, in the form com.amazonaws.region.service.
      '';
    };

  };
}
