{ config, lib, uuid, name, ... }:

with lib;

{

  options = {

    name = mkOption {
      default = "charon-${uuid}-${name}";
      type = types.str;
      description = "Name of the IAM role.";
    };

    accessKeyId = mkOption {
      type = types.str;
      description = "The AWS Access Key ID.";
    };

    policy = mkOption {
      type = types.str;
      description = "The IAM policy definition (in JSON format).";
    };

    assumeRolePolicy = mkOption {
      type = types.str;
      description = "The IAM AssumeRole policy definition (in JSON format). Empty string (default) uses the existing Assume Role Policy.";
      default = "";
    };

  };

}
