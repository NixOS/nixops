{ config, lib, ... }:

with lib;

{

  options = {

    region = mkOption {
      type = types.str;
      description = "AWS region.";
    };

    accessKeyId = mkOption {
      type = types.str;
      description = "The AWS Access Key ID.";
    };

  } // import ./common-ec2-options.nix { inherit lib; };

  config = {
    _type = "elastic-file-system";
  };

}
