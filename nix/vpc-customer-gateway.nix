{ config, lib, uuid, name, ... }:

with lib;
{
  options = {

    name = mkOption {
      default = "charon-${uuid}-${name}";
      type = types.str;
      description = "Name of the VPC customer gateway.";
    };
    
    accessKeyId = mkOption {
      default = "";
      type = types.str;
      description = "The AWS Access Key ID.";
    };

    region = mkOption {
      type = types.str;
      description = "AWS region.";
    };

    bgpAsn = mkOption {
      type = types.int;
      description = ''
        For devices that support BGP, the customer gateway's BGP ASN.
      '';
    };

    publicIp = mkOption {
      type = types.str;
      description = ''
        The Internet-routable IP address for the customer gateway's outside interface.
        The address must be static.
      '';
    };

    type = mkOption {
      type = types.str;
      description = ''
        The type of VPN connection that this customer gateway supports (ipsec.1 ).
      '';
    };

  } // import ./common-ec2-options.nix { inherit lib; }; 

  config._type = "vpc-customer-gateway";
}
