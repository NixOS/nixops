{ config, lib, pkgs, uuid, name, ... }:

with lib;
with (import ./lib.nix lib);
{

  options = {

    name = mkOption {
      example = "my-queue";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = ''
        Description of the Azure queue.
        This is the <literal>Name</literal> tag of the queue.
      '';
    };

    accessKey = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = "Access key for the storage service if not managed by NixOps.";
    };

    storage = mkOption {
      example = "xxx-my-storage";
      type = types.either types.str (resource "azure-storage");
      description = "The name or resource of an Azure storage in which the queue is to be created.";
    };

    metadata = mkOption {
      default = {};
      example = { loglevel = "warn"; };
      type = types.attrsOf types.str;
      description = "Metadata name/value pairs to associate with the queue.";
    };

    acl.signedIdentifiers = (import ./azure-signed-identifiers.nix lib);

  };

  config._type = "azure-queue";

}
