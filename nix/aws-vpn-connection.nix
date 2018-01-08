{ config, lib, uuid, name, ... }:

with import ./lib.nix lib;
with lib;

{
  imports = [ ./common-ec2-auth-options.nix ];

  options = {

    name = mkOption {
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the AWS VPN connection.";
    };
    
    vpnGatewayId = mkOption {
      type = types.either types.str (resource "aws-vpn-gateway");
      apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type;
      description = ''
        The ID of the VPN gateway.
      '';
    };

    customerGatewayId = mkOption {
      type = types.either types.str (resource "vpc-customer-gateway");
      apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type;
      description = ''
        The ID of the customer gateway.
      '';
    };

    staticRoutesOnly = mkOption {
      default = false;
      type = types.bool;
      description = ''
        Indicates whether the VPN connection uses static routes only.
        Static routes must be used for devices that don't support BGP.
      '';
    };

  } // import ./common-ec2-options.nix { inherit lib; };

  config._type = "aws-vpn-connection";
}
