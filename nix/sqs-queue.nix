{ config, pkgs, uuid, name, ... }:

with pkgs.lib;

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

  };

}
