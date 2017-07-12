{ config, lib, uuid, name, ... }:

with import ./lib.nix lib;
with lib;
{
  options = {
    
    name = mkOption {
      default = "charon-${uuid}-${name}";
      type = types.str;
      description = "Name of the VPC network interface.";
    };
    
    accessKeyId = mkOption {
      type = types.str;
      description = "The AWS Access Key ID.";
    };

    region = mkOption {
      type = types.str;
      description = "AWS region.";
    };

    subnetId = mkOption {
      type = types.either types.str (resource "vpc-subnet");
      apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type;
      description = ''
        Subnet Id to create the ENI in. 
      '';
    };

    description = mkOption {
      default = "";
      type = types.str;
      description = ''
        A description for the network interface.
      '';
    };

    securityGroups = mkOption {
      default = null;
      type = types.listOf (types.either types.str (resource "ec2-security-group"));
      description = ''
        The IDs of one or more security groups.
      '';
    };

    primaryPrivateIpAddress = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = ''
        The primary private IPv4 address of the network interface. If you don't
        specify an IPv4 address, Amazon EC2 selects one for you from the subnet's
        IPv4 CIDR range.
      '';
    }; 

    privateIpAddresses = mkOption {
      default = [];
      type = types.listOf types.str;
      description = ''
        One or more secondary private IPv4 addresses.
      '';
    };

    secondaryPrivateIpAddressCount = mkOption {
      default = null;
      type = types.nullOr types.int;
      description = ''
        The number of secondary private IPv4 addresses to assign to a network interface.
        When you specify a number of secondary IPv4 addresses, Amazon EC2 selects these
        IP addresses within the subnet's IPv4 CIDR range.
        You can't specify this option and specify privateIpAddresses in the same time.
      '';
    };

    sourceDestCheck = mkOption {
      default = true;
      type = types.bool;
      description = ''
        Indicates whether source/destination checking is enabled.
        Default value is true. 
      '';
    };

  };

  config = {
    _type = "vpc-network-interface";
  };
}
