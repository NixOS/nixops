{ config, lib, uuid, name, ... }:

with lib;

{

  options = {

    region = mkOption {
      example = "us-east-1";
      type = types.str;
      description = "AWS region.";
    };

    accessKeyId = mkOption {
      default = "";
      type = types.str;
      description = "The AWS Access Key ID.";
    };

    address = mkOption {
      default = "_UNKNOWN_ELASTIC_IP_"; # FIXME: don't set a default
      type = types.str;
      description = "The elastic IP address, set by NixOps.";
    };

    vpc = mkOption {
      default = false;
      type = types.bool;
      description = ''
        Whether to allocate the address for use with instances in a VPC.
      '';
    };

    persistOnDestroy = mkOption {
      default = false;
      type = types.bool;
      description = ''
        If set to true <command>nixops destroy</command> won't delete
        the elastic IP on destroy.
      '';
    };

  };

  config._type = "elastic-ip";

}
