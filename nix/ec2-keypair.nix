{ config, pkgs, uuid, name, ... }:

with pkgs.lib;

{

  options = {

    name = mkOption {
      default = "charon-${uuid}-${name}";
      type = types.uniq types.string;
      description = "Name of the EC2 key pair.";
    };

    region = mkOption {
      type = types.uniq types.string;
      description = "Amazon EC2 region.";
    };

    accessKeyId = mkOption {
      default = "";
      type = types.uniq types.string;
      description = "The AWS Access Key ID.";
    };

  };

}
