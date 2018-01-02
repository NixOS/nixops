{ config, lib, uuid, name, ... }:

with import ./lib.nix lib;
with lib;

{
  imports = [ ./common-ec2-auth-options.nix ];

  options = {

    name = mkOption {
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the subnet VPC.";
    };

    vpcId = mkOption {
      type = types.either types.str (resource "vpc");
      apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type;
      description = ''
        The ID of the VPC where the subnet will be created
      '';
    };

    cidrBlock = mkOption {
      type = types.str;
      description = "The CIDR block for the VPC subnet";
    };

    ipv6CidrBlock = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = ''
        The IPv6 network range for the subnet, in CIDR notation.
        The subnet size must use a /64 prefix length.
      '';
    };

    zone = mkOption {
      type = types.str;
      description = ''
        The availability zone for the VPC subnet.
        By default AWS selects one for you.
      '';
    };

    mapPublicIpOnLaunch = mkOption {
      default = false;
      type = types.bool;
      description = ''
        Indicates whether instances launched into the subnet should be assigned
        a public IP in launch. Default is false.
      '';
    };
    
    subnetId = mkOption {
      default = "";
      type = types.str;
      description = "The VPC subnet id generated from AWS. This is set by NixOps";
    };

  } // import ./common-ec2-options.nix { inherit lib; } ;

  config._type = "vpc-subnet";

}
