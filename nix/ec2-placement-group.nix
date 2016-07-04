{ config, lib, uuid, name, ... }:

with lib;

{

  options = {

    name = mkOption {
      default = "charon-${uuid}-${name}";
      type = types.str;
      description = "Name of the placement group.";
    };

    strategy = mkOption {
      default = "cluster";
      type = types.str;
      description = "The placement strategy of the new placement group. Currently, the only acceptable value is “cluster”.";
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

  config._type = "ec2-placement-group";

}
