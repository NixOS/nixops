{ config, lib, uuid, name, ... }:

with import ./lib.nix lib;
with lib;
{
  imports = [ ./common-ec2-auth-options.nix ];

  options = {

    name = mkOption {
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the VPC route table.";
    };
    
    vpcId = mkOption {
      type = types.either types.str (resource "vpc");
      apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type;
      description = ''
        The ID of the VPC where the route table will be created
      '';
    };

    propagatingVgws = mkOption {
      default = [];
      type =  types.listOf (types.either types.str (resource "aws-vpn-gateway"));
      apply = map (x: if builtins.isString x then x else "res-" + x._name + "." + x._type + ".vpnGatewayId");
      description = ''
        A list of VPN gateways for propagation.
      '';
    };

  } // import ./common-ec2-options.nix { inherit lib; };

  config._type = "vpc-route-table";
}
