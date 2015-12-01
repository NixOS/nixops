{ config, lib, pkgs, uuid, name, ... }:

with lib;
with (import ./lib.nix lib);
{

  options = (import ./azure-credentials.nix lib "disk") // {

    name = mkOption {
      example = "my-os-image";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Description of the Azure OS image. This is the <literal>Name</literal> tag of the image.";
    };

    mediaLink = mkOption {
      example = "http://mystorage.blob.core.windows.net/mycontainer/mydisk";
      type = types.str;
      description = ''
        The URL of the Azure BLOB storage where the VHD file for the OS image is located.
        The BLOB must exist.
      '';
    };

    label = mkOption {
      type = types.str;
      description = "Human-friendly label for the OS image up to 100 characters in length.";
    };

    os = mkOption {
      type = types.str;
      description = ''
        The operating system the OS image contains.
        Valid values are: Linux, Windows.
      '';
    };

  };

  config._type = "azure-os-image";

}
