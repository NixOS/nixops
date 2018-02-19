{ config, lib, uuid, name, ... }:

with lib;

{

  options = {

    name = mkOption {
      default = "charon-${uuid}-${name}";
      type = types.str;
      description = "Name of the SNS topic.";
    };

    region = mkOption {
      type = types.str;
      description = "AWS region.";
    };

    accessKeyId = mkOption {
      type = types.str;
      description = "The AWS Access Key ID.";
    };

    displayName = mkOption  {
      default = null;
      type = types.nullOr (types.str);
      description = "Display name of the topic";
    };

    policy = mkOption {
      default = "";
      type = types.str;
      description = "Policy to apply to the SNS topic.";
    };

    subscriptions = mkOption {
      description = "List of subscriptions to apply to the topic.";
      default = [];
      type = with types; listOf (submodule {
        options = {
          protocol = mkOption {
            default = null;
            description = "The protocol to use.";
            type = types.str;
          };
          endpoint = mkOption {
            default = null;
            description = "The endpoint to send data to.";
            type = types.str;
          };
        };
      });
    };

    arn = mkOption {
      default = "";
      type = types.str;
      description = "Amazon Resource Name (ARN) of the SNS topic. This is set by NixOps.";
    };

  };

  config = {
    _type = "sns-topic";
  };
}
