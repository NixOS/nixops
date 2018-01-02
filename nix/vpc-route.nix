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
      description = "Name of the VPC route.";
    };
    
    routeTableId = mkOption {
      type = types.either types.str (resource "vpc-route-table");
      apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type;
      description = ''
        The ID of the VPC route table
      '';
    };

    destinationCidrBlock = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = ''
        The IPv4 CIDR address block used for the destination match.
      '';
    };

    destinationIpv6CidrBlock = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = ''
        The IPv6 CIDR block used for the destination match.
      '';
    };

    gatewayId = mkOption {
      default = null;
      type = types.nullOr (types.either types.str (resource "vpc-internet-gateway"));
      apply = x: if (builtins.isString x || builtins.isNull x) then x else "res-" + x._name + "." + x._type + ".internetGatewayId";
      description = ''
        The ID of an Internet gateway or virtual private gateway attached to your VPC.
      '';
    };

    egressOnlyInternetGatewayId = mkOption {
      default = null;
      type = types.nullOr (types.either types.str (resource "vpc-egress-only-internet-gateway"));
      apply = x: if (builtins.isString x || builtins.isNull x) then x else "res-" + x._name + "." + x._type + ".egressOnlyInternetGatewayId";
      description = ''
        [IPv6 traffic only] The ID of an egress-only Internet gateway.
      '';
    };

    instanceId = mkOption {
      default = null;
      type = types.nullOr (types.either types.str machine);
      apply = x: if (builtins.isString x || builtins.isNull x) then x else "res-" + x._name + ".ec2." + "vm_id";
      description = ''
        The ID of a NAT instance in your VPC. The operation fails if you specify an
        instance ID unless exactly one network interface is attached.
      '';
    };

    natGatewayId = mkOption {
      default = null;
      type = types.nullOr (types.either types.str (resource "vpc-nat-gateway"));
      apply = x: if (builtins.isString x || builtins.isNull x) then x else "res-" + x._name + "." + x._type;
      description = ''
        The ID of a NAT gateway.
      '';
    };

    networkInterfaceId = mkOption {
      default = null;
      type = types.nullOr (types.either types.str (resource "vpc-network-interface"));
      apply = x: if (builtins.isString x || builtins.isNull x) then x else "res-" + x._name + "." + x._type;
      description = ''
        The ID of a network interface.
      '';
    };

    #TODO add VPC peering connection

  };

  config._type = "vpc-route";
}
