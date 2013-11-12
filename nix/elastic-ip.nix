{ config, pkgs, uuid, name, ... }:

with pkgs.lib;

{

  options = {

    region = mkOption {
      example = "us-east-1";
      type = types.str;
      description = "Amazon EC2 region.";
    };

    accessKeyId = mkOption {
      type = types.str;
      description = "The AWS Access Key ID.";
    };

    address = mkOption {
      default = "_UNKNOWN_ELASTIC_IP_"; # FIXME: don't set a default
      type = types.str;
      description = "The elastic IP address, set by NixOps.";
    };

  };

}
