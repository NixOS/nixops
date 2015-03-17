{ config, pkgs, lib, uuid, name, ... }:

with lib;
with import ./lib.nix lib;
{

  options = (import ./gce-credentials.nix lib "disk") // {

    name = mkOption {
      example = "big-fat-disk";
      default = "n-${shorten_uuid uuid}-${name}";
      type = types.str;
      description = "Description of the GCE disk.  This is the <literal>Name</literal> tag of the disk.";
    };

    region = mkOption {
      example = "europe-west1-b";
      type = types.str;
      description = "The GCE datacenter in which the disk should be created.";
    };

    size = mkOption {
      default = null;
      example = 100;
      type = types.nullOr types.int;
      description = ''
        Disk size (in gigabytes).  This may be left unset if you are
        creating the disk from a snapshot or image, in which case the
        size of the disk will be equal to the size of the snapshot or image.
        You can set a size larger than the snapshot or image,
        allowing the disk to be larger than the snapshot from which it is
        created.
      '';
    };

    snapshot = mkOption {
      default = null;
      example = "snap-1cbda474";
      type = types.nullOr types.str;
      description = ''
        The snapshot name from which this disk will be created. If
        not specified, an empty disk is created.  Changing the
        snapshot name has no effect if the disk already exists.
      '';
    };

    image = mkOption {
      default = null;
      example = "image-2cfda297";
      type = types.nullOr ( types.either types.str (resource "gce-image") );
      description = ''
        The image name or resource from which this disk will be created. If
        not specified, an empty disk is created.  Changing the
        image name has no effect if the disk already exists.
      '';
    };

    diskType = mkOption {
      default = "standard";
      type = types.addCheck types.str
               (v: elem v [ "standard" "ssd" ]);
      description = ''
        The disk storage type (standard/ssd).
      '';
    };

  };

  config = 
    (mkAssert ( (config.snapshot == null) || (config.image == null) )
              "Disk can not be created from both a snapshot and an image at once"
      (mkAssert ( (config.size != null) || (config.snapshot != null) || (config.image != null) )
                "Disk size is required unless it is created from an image or snapshot" {
          _type = "gce-disk";
        }
      )
    );

}
