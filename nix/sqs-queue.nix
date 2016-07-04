{ config, lib, uuid, name, ... }:

with lib;

{

  options = {

    name = mkOption {
      default = "charon-${uuid}-${name}";
      type = types.str;
      description = "Name of the SQS queue.";
    };

    region = mkOption {
      type = types.str;
      description = "AWS region.";
    };

    accessKeyId = mkOption {
      type = types.str;
      description = "The AWS Access Key ID.";
    };

    visibilityTimeout = mkOption {
      default = 30;
      type = types.int;
      description =
        ''
          The time interval in seconds after a message has been
          received until it becomes visible again.
        '';
    };

    url = mkOption {
      default = ""; # FIXME: don't set a default
      type = types.str;
      description = "URL of the queue. This is set by NixOps.";
    };

    arn = mkOption {
      default = ""; # FIXME: don't set a default
      type = types.str;
      description = "Amazon Resource Name (ARN) of the queue. This is set by NixOps.";
    };

  };

}
