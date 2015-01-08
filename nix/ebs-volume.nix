{ config, pkgs, uuid, name, ... }:

with pkgs.lib;

{

  options = {

    name = mkOption {
      example = "My Big Fat Disk";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Description of the EBS volume.  This is the <literal>Name</literal> tag of the disk.";
    };

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

    size = mkOption {
      example = 100;
      type = types.int;
      description = ''
        Volume size (in gigabytes).  This may be left unset if you are
        creating the volume from a snapshot, in which case the size of
        the volume will be equal to the size of the snapshot.
        However, you can set a size larger than the snapshot, allowing
        the volume to be larger than the snapshot from which it is
        created.
      '';
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

  };

  config = {
    _type = "ebs-volume";
    size = mkIf (config.snapshot != "") (mkDefault 0);
  };

}
