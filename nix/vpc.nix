{ config, lib, uuid, name, ... }:

with lib;

{

  options = {

    name = mkOption {
      default = "charon-${uuid}-${name}";
      type = types.str;
      description = "Name of the VPC.";
    };

    accessKeyId = mkOption {
      type = types.str;
      description = "The AWS Access Key ID.";
    };

    region = mkOption {
      type = types.str;
      description = "AWS region.";
    };

    cidrBlock = mkOption {
      type = types.str;
      description = "The CIDR block for the VPC";
    };

    instanceTenancy = mkOption {
      type = types.str;
      description = ''
        The supported tenancy options for instances launched
        into the VPC. Valid values are "default" and "dedicated".
      '';
    };
    
    enableDnsSupport = mkOption {
      default = null;
      type = types.nullOr types.bool;
      description = ''
        Specifies whether the DNS server provided by Amazon is enabled for the VPC.
      ''; 
    };
    
    enableDnsHostnames = mkOption {
      default = null;
      type = types.nullOr types.bool;
      description = ''
        Specifies whether DNS hostnames are provided for the instances launched in this VPC.
        You can only set this attribute to true if EnableDnsSupport is also true.
      '';
    };

    enableClassicLink = mkOption {
      default = null;
      type = types.nullOr types.bool;
      description = ''
        Enables a VPC for ClassicLink. You can then link EC2-Classic instances to your
        ClassicLink-enabled VPC to allow communication over private IP addresses.
        You cannot enable your VPC for ClassicLink if any of your VPC’s route tables
        have existing routes for address ranges within the 10.0.0.0/8 IP address range
        , excluding local routes for VPCs in the 10.0.0.0/16 and 10.1.0.0/16 IP address ranges.
      '';
    };

  };

}
