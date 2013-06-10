{ config, lib, uuid, name, ... }:

with lib;

{

  options = {

    name = mkOption {
      default = "charon-${uuid}-${name}";
      type = types.uniq types.string;
      description = "Name of the SQS queue.";
    };

    region = mkOption {
      type = types.uniq types.string;
      description = "Amazon EC2 region.";
    };

    accessKeyId = mkOption {
      type = types.uniq types.string;
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
      type = types.uniq types.string;
      description = "URL of the queue. This is set by NixOps.";
    };

    arn = mkOption {
      default = ""; # FIXME: don't set a default
      type = types.uniq types.string;
      description = "Amazon Resource Name (ARN) of the queue. This is set by NixOps.";
    };

  };

}
