{ config, lib, pkgs, uuid, name, ... }:

with lib;
with import ./lib.nix lib;

{

  options = (import ./gce-credentials.nix lib "image") // {

    name = mkOption {
      example = "my-bootstrap-image";
      default = "n-${shorten_uuid uuid}-${name}";
      type = types.str;
      description = "Description of the GCE image. This is the <literal>Name</literal> tag of the image.";
    };

    sourceUri = mkOption {
      example = "gs://nixos-images/nixos-14.10pre-git-x86_64-linux.raw.tar.gz";
      type = types.str;
      description = "The full Google Cloud Storage URL where the disk image is stored.";
    };

    description = mkOption {
      default = null;
      example = "bootstrap image for the DB node";
      type = types.nullOr types.str;
      description = "An optional textual description of the image.";
    };

  };

  config._type = "gce-image";

}
