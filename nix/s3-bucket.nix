{ config, lib, uuid, name, ... }:

with lib;

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
      default = "arn:aws:s3:::${config.name}";
      type = types.str;
      description = "Amazon Resource Name (ARN) of the S3 bucket. This is set by NixOps.";
    };

    policy = mkOption {
      type = types.str;
      default = "";
      description = "The JSON Policy string to apply to the bucket.";
    };

    lifeCycle = mkOption {
      type = types.str;
      default = "";
      description = "The JSON lifecycle management string to apply to the bucket.";
    };

    versioning = mkOption {
      default = "Suspended";
      type = types.enum [ "Suspended" "Enabled" ];
      description = "Whether to enable S3 versioning or not. Valid values are 'Enabled' or 'Suspended'";
    };

    persistOnDestroy = mkOption {
      default = false;
      type = types.bool;
      description = ''
        If set to true <command>nixops destroy</command> won't delete the bucket
        on destroy.
      '';
    };

    website.enabled = mkOption {
      type = types.bool;
      default = false;
      description = "Whether to serve the S3 bucket as public website.";
    };

    website.suffix = mkOption {
      type = types.str;
      default = "index.html";
      description = "A suffix that is appended to a request that is for a directory on the website endpoint.";
    };

    website.errorDocument = mkOption {
      type = types.str;
      default = "";
      description = "The S3 key to serve when response is an error.";
    };


  };

}
