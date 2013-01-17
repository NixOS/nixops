{ config, pkgs, uuid, name, ... }:

with pkgs.lib;

{

  options = {

    name = mkOption {
      default = "charon-${uuid}-${name}";
      type = types.uniq types.string;
      description = "Name of the S3 bucket.";
    };

    region = mkOption {
      type = types.uniq types.string;
      description = "Amazon S3 region.";
    };

    accessKeyId = mkOption {
      type = types.uniq types.string;
      description = "The AWS Access Key ID.";
    };

  };

}
