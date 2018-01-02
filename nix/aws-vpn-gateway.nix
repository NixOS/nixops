{ config, lib, uuid, name, ... }:

with import ./lib.nix lib;
with lib;

{
  imports = [ ./common-ec2-auth-options.nix ];

  options = {

    name = mkOption {
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the AWS VPN gateway.";
    };
    
    zone = mkOption {
      # NOTE: We're making this required in NixOps but the api can handle
      # choosing the zone. Making this required will prevent having
      # the diff engine trigger the zone handler in each deploy.
      type = types.str;
      description = "AWS availability zone.";
    };

    vpcId = mkOption {
      type = types.either types.str (resource "vpc");
      apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type;
      description = ''
        The ID of the VPC where the VPN gateway will be attached.
      '';
    };
  } // import ./common-ec2-options.nix { inherit lib; };

  config._type = "aws-vpn-gateway";
}
