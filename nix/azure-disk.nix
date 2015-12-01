{ config, lib, pkgs, uuid, name, ... }:

with lib;
with (import ./lib.nix lib);
{

  options = (import ./azure-credentials.nix lib "disk") // {

    name = mkOption {
      example = "my-disk";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Description of the Azure disk. This is the <literal>Name</literal> tag of the disk.";
    };

    mediaLink = mkOption {
      example = "http://mystorage.blob.core.windows.net/mycontainer/mydisk";
      type = types.str;
      description = ''
        The URL of the Azure BLOB storage where the VHD file for the disk is located.
        The BLOB must exist.
      '';
    };

    label = mkOption {
      type = types.str;
      description = "Human-friendly label for the disk up to 100 characters in length.";
    };

    os = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = ''
        The operating system the disk contains(if any).
        Valid values are: null, Linux, Windows.
      '';
    };

  };

  config._type = "azure-disk";

}
