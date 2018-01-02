{ config, lib, uuid, name, ... }:

with lib;

{
  imports = [ ./common-ec2-auth-options.nix ];

  options = {

    name = mkOption {
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the VPC.";
    };

    cidrBlock = mkOption {
      type = types.str;
      description = "The CIDR block for the VPC";
    };

    instanceTenancy = mkOption {
      default = "default";
      type = types.str;
      description = ''
        The supported tenancy options for instances launched
        into the VPC. Valid values are "default" and "dedicated".
      '';
    };
    
    enableDnsSupport = mkOption {
      default = false;
      type = types.bool;
      description = ''
        Specifies whether the DNS server provided by Amazon is enabled for the VPC.
      ''; 
    };
    
    enableDnsHostnames = mkOption {
      default = false;
      type = types.bool;
      description = ''
        Specifies whether DNS hostnames are provided for the instances launched in this VPC.
        You can only set this attribute to true if EnableDnsSupport is also true.
      '';
    };

    enableClassicLink = mkOption {
      default = false;
      type = types.bool;
      description = ''
        Enables a VPC for ClassicLink. You can then link EC2-Classic instances to your
        ClassicLink-enabled VPC to allow communication over private IP addresses.
        You cannot enable your VPC for ClassicLink if any of your VPC’s route tables
        have existing routes for address ranges within the 10.0.0.0/8 IP address range
        , excluding local routes for VPCs in the 10.0.0.0/16 and 10.1.0.0/16 IP address ranges.
      '';
    };

    amazonProvidedIpv6CidrBlock = mkOption {
      default = false;
      type = types.bool;
      description = ''
        Requests an Amazon-provided IPv6 CIDR block with a /56 prefix length for the VPC.
        You cannot specify the range of IP addresses, or the size of the CIDR block.
      '';
    };

    vpcId = mkOption {
      default = "";
      type = types.str;
      description = "The VPC id generated from AWS. This is set by NixOps";
    };

  } // import ./common-ec2-options.nix { inherit lib; };

  config._type = "vpc";
}
