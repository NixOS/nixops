{ config, lib, uuid, name, ... }:

with lib;

{

  options = {

    name = mkOption {
      default = "charon-${uuid}-${name}";
      type = types.str;
      description = "Name of the cloudwatch log stream.";
    };

    accessKeyId = mkOption {
      type = types.str;
      description = "The AWS Access Key ID.";
    };

    region = mkOption {
      type = types.str;
      description = "AWS region.";
    };

    logGroupName = mkOption {
      type = types.str;
      description = "The name of the log group under which the log stream is to be created.";
    };

    arn = mkOption {
      default = "";
      type = types.str;
      description = "Amazon Resource Name (ARN) of the cloudwatch log stream. This is set by NixOps.";
    };

  };

}
