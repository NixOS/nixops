{ config, lib, uuid, name, ... }:

with lib;

{

  options = {

    name = mkOption {
      default = "charon-${uuid}-${name}";
      type = types.str;
      description = "Name of the cloudwatch log group.";
    };

    accessKeyId = mkOption {
      type = types.str;
      description = "The AWS Access Key ID.";
    };

    region = mkOption {
      type = types.str;
      description = "AWS region.";
    };

    retentionInDays = mkOption {
      default = null;
      type = types.nullOr types.int;
      description = "How long to store log data in a log group";
    };

    arn = mkOption {
      default = "";
      type = types.str;
      description = "Amazon Resource Name (ARN) of the cloudwatch log group. This is set by NixOps.";
    };

  };

}
