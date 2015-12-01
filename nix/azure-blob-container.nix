{ config, lib, pkgs, uuid, name, ... }:

with lib;
with (import ./lib.nix lib);
{

  options = (import ./azure-credentials.nix lib "BLOB container") // {

    name = mkOption {
      example = "my-blob-container";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = ''
        Description of the Azure BLOB container.
        Must include only lower-case characters.
        This is the <literal>Name</literal> tag of the container.
      '';
    };

    accessKey = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = "Access key for the storage service if not managed by NixOps.";
    };

    acl = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = "Permissions for the container: null(private), 'container' or 'blob'.";
    };

    storage = mkOption {
      example = "xxx-my-storage";
      type = types.either types.str (resource "azure-storage");
      description = "The name or resource of an Azure storage in which the container is to be created.";
    };

    metadata = mkOption {
      default = {};
      example = { loglevel = "warn"; };
      type = types.attrsOf types.str;
      description = "Metadata name/value pairs to associate with the container.";
    };

  };

  config._type = "azure-blob-container";

}
