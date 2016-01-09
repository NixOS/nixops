{ config, lib, pkgs, uuid, name, ... }:

with lib;
with (import ./lib.nix lib);
{

  options = {

    name = mkOption {
      example = "my-file";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Description of the Azure file. This is the <literal>Name</literal> tag of the file.";
    };

    accessKey = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = "Access key for the storage service if the container is not managed by NixOps.";
    };


    filePath = mkOption {
      example = "path/to/source/file";
      type = types.str;
      description = "Path to the local file to upload.";
    };

    share = mkOption {
      default = null;
      example = "xxx-my-share";
      type = types.nullOr (types.either types.str (resource "azure-share"));
      description = ''
          The name or resource of an Azure share in which the file is to be stored.
          Must specify at least one of directory or share.
      '';
    };

    directoryPath = mkOption {
      default = null;
      example = "dir1/dir2";
      type = types.nullOr types.str;
      description = ''
        The path to the directory in which the file is to be created.
        If not specified, the file will be created in the root of the share.
        Must also specify Azure share.
      '';
    };

    directory = mkOption {
      default = null;
      example = "xxx-my-directory";
      type = types.nullOr (types.either types.str (resource "azure-directory"));
      description = ''
        The name or resource of an Azure directory in which the file is to be created.
        If not specified, the file will be created in the root of the share.
        Must specify at least one of directory or share.
      '';
    };

    storage = mkOption {
      default = null;
      example = "xxx-my-storage";
      type = types.nullOr (types.either types.str (resource "azure-storage"));
      description = "The name or resource of an Azure storage if the share is not managed by NixOps.";
    };

    contentEncoding = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = ''
          Specifies which content encodings have been applied to
          the file. This value is returned to the client when the Get File
          operation is performed on the file resource and can be used
          to decode the file content.
      '';
    };

    contentLanguage = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = "Specifies the natural languages used by this resource.";
    };

#    contentLength = mkOption {
#      default = null;
#      type = types.nullOr types.int;
#      description = ''
#          File size.
#      '';
#    };

    contentType = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = "The MIME content type of the file.";
    };

    cacheControl = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = "The File service stores this value but does not use or modify it.";
    };

    contentDisposition = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = ''
          The Content-Disposition response header field conveys additional
          information about how to process the response payload, and also
          can be used to attach additional metadata. For example, if set
          to "attachment", Content-Disposition indicates that the user-agent
          should not display the response, but instead show a Save As dialog.
      '';
    };

    metadata = mkOption {
      default = {};
      example = { loglevel = "warn"; };
      type = types.attrsOf types.str;
      description = "Metadata name/value pairs to associate with the File.";
    };

  };

  config._type = "azure-file";

}
