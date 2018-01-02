{ config, lib, ... }:

with lib;

{
  options = {
    accessKeyId = mkOption {
      default = "";
      type = types.str;
      description = ''
        The AWS Access Key ID.
      '';
    };
    region = mkOption {
      type = types.str;
      description = ''
        AWS region.
      '';
    };
  };
}
