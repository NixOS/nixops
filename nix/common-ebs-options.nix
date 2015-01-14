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

  };

}
