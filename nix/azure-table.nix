{ config, lib, pkgs, uuid, name, ... }:

with lib;
with (import ./lib.nix lib);
{

  options = {

    name = mkOption {
      example = "my-queue";
      default = "nixops${lib.replaceChars [ "-" ] [ "" ] uuid}${name}";
      type = types.str;
      description = ''
        Description of the Azure table.
        The name must not contain dashes.
        This is the <literal>Name</literal> tag of the table.
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
      description = "The name or resource of an Azure storage in which the table is to be created.";
    };

    acl.signedIdentifiers = (import ./azure-signed-identifiers.nix lib);

  };

  config._type = "azure-table";

}
