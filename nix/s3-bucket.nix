{ config, pkgs, uuid, name, ... }:

with pkgs.lib;

{

  options = {

    name = mkOption {
      default = "charon-${uuid}-${name}";
      type = types.str;
      description = "Name of the S3 bucket.";
    };

    region = mkOption {
      type = types.str;
      description = "Amazon S3 region.";
    };

    accessKeyId = mkOption {
      type = types.str;
      description = "The AWS Access Key ID.";
    };

    arn = mkOption {
      default = "arn:aws:s3:::${config.name}"; # FIXME: don't set a default
      type = types.str;
      description = "Amazon Resource Name (ARN) of the S3 bucket. This is set by NixOps.";
    };

    policyJson = mkOption {
      type = types.str;
      default = "";
      description = "The JSON Policy string to apply to the bucket.";
    };

  };

}
