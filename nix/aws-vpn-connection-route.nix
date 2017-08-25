{ config, lib, uuid, name, ... }:

with import ./lib.nix lib;
with lib;
{
  options = {
    name = mkOption {
      default = "charon-${uuid}-${name}";
      type = types.str;
      description = "Name of the VPN connection route.";
    };
    
    accessKeyId = mkOption {
      type = types.str;
      description = "The AWS Access Key ID.";
    };

    region = mkOption {
      type = types.str;
      description = "AWS region.";
    };

    vpnConnectionId = mkOption {
      type = types.either types.str (resource "aws-vpn-connection");
      apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type;
      description = ''
        The ID of the VPN connection.
      '';
    };

    destinationCidrBlock = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = ''
        The IPv4 CIDR address block used for the destination match.
      '';
    };
  };
}
