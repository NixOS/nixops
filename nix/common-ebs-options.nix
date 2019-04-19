# Options shared between the EBS resource type and the
# deployment.ec2.blockDeviceMapping/fileSystems.*.ec2 options in EC2
# instances.

{ config, lib, ... }:

with lib;

{

  options = {

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

    iops = mkOption {
      default = null;
      type = types.nullOr types.int;
      description = ''
        The provisioned IOPS you want to associate with this EBS volume.
      '';
    };

    volumeType = mkOption {
      default = if config.iops == null then "standard" else "io1";
      type = types.enum [ "standard" "io1" "gp2" "st1" "sc1" ];
      description = ''
        The volume type for the EBS volume, which must be one of
        <literal>"standard"</literal> (a magnetic volume),
        <literal>"io1"</literal> (a provisioned IOPS SSD volume) or
        <literal>"gp2"</literal> (a general purpose SSD volume).
        <literal>"st1"</literal> (a throughput optimized HDD volume).
        <literal>"sc1"</literal> (a cold HDD volume).
      '';
    };

  };

}
