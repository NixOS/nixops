{ config, pkgs, uuid, name, ... }:

with pkgs.lib;

{

  options = {

    region = mkOption {
      example = "us-east-1";
      type = types.uniq types.string;
      description = "Amazon EC2 region.";
    };

    accessKeyId = mkOption {
      type = types.uniq types.string;
      description = "The AWS Access Key ID.";
    };

    address = mkOption {
      default = "_UNKNOWN_ELASTIC_IP_"; # FIXME: don't set a default
      type = types.uniq types.string;
      description = "The elastic IP address, set by NixOps.";
    };

  };

}
