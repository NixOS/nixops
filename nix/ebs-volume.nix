{ config, lib, uuid, name, ... }:

with lib;

{

  imports = [ ./common-ebs-options.nix ];

  options = {

    region = mkOption {
      example = "us-east-1";
      type = types.str;
      description = "Amazon EC2 region.";
    };

    zone = mkOption {
      example = "us-east-1c";
      type = types.str;
      description = ''
        The EC2 availability zone in which the volume should be
        created.
      '';
    };

    accessKeyId = mkOption {
      type = types.str;
      default = "";
      description = "The AWS Access Key ID.";
    };

    snapshot = mkOption {
      default = "";
      example = "snap-1cbda474";
      type = types.str;
      description = ''
        The snapshot ID from which this volume will be created.  If
        not specified, an empty volume is created.  Changing the
        snapshot ID has no effect if the volume already exists.
      '';
    };

  } // import ./common-ec2-options.nix { inherit lib; };

  config = {
    _type = "ebs-volume";
    size = mkIf (config.snapshot != "") (mkDefault 0);
  };

}
