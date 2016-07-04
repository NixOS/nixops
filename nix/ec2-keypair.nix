{ config, lib, uuid, name, ... }:

with lib;

{

  options = {

    name = mkOption {
      default = "charon-${uuid}-${name}";
      type = types.str;
      description = "Name of the EC2 key pair.";
    };

    region = mkOption {
      type = types.str;
      description = "AWS region.";
    };

    accessKeyId = mkOption {
      default = "";
      type = types.str;
      description = "The AWS Access Key ID.";
    };

  };

  config._type = "ec2-keypair";

}
