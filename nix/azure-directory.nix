{ config, lib, pkgs, uuid, name, ... }:

with lib;
with (import ./lib.nix lib);
{

  options = {

    name = mkOption {
      example = "my-directory";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = ''
        Description of the Azure directory.
        This is the <literal>Name</literal> tag of the directory.
      '';
    };

    accessKey = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = "Access key for the storage service if not managed by NixOps.";
    };

    parentDirectoryPath = mkOption {
      default = null;
      example = "dir1/dir2";
      type = types.nullOr types.str;
      description = ''
        The path to the parent directory in which the directory is to be created.
        Should only be used if the parent directory is not managed by NixOps.
        Must also specify Azure share.
      '';
    };

    parentDirectory = mkOption {
      default = null;
      example = "xxx-my-directory";
      type = types.nullOr (types.either types.str (resource "azure-directory"));
      description = ''
        The name or resource of an Azure directory in which the directory is to be created.
        Must specify at least one of parentDirectory or share.
      '';
    };

    share = mkOption {
      default = null;
      example = "xxx-my-share";
      type = types.nullOr (types.either types.str (resource "azure-share"));
      description = ''
        The name or resource of an Azure share in which the directory is to be created.
        Must specify at least one of parentDirectory or share.
      '';
    };

    storage = mkOption {
      default = null;
      example = "xxx-my-storage";
      type = types.nullOr (types.either types.str (resource "azure-storage"));
      description = ''
        The name or resource of an Azure storage in which the directory is to be created.
        Optional if parentDirectory or share are managed by NixOps.
      '';
    };

    metadata = mkOption {
      default = {};
      example = { loglevel = "warn"; };
      type = types.attrsOf types.str;
      description = "Metadata name/value pairs to associate with the directory.";
    };

  };

  config._type = "azure-directory";

}
