{ config, pkgs, uuid, name, ... }:

with pkgs.lib;
with (import ./lib.nix pkgs);
{

  options = (import ./azure-credentials.nix pkgs "BLOB") // {

    name = mkOption {
      example = "my-blob";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Description of the Azure BLOB. This is the <literal>Name</literal> tag of the BLOB.";
    };

    accessKey = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = "Access key for the storage service if the container is not managed by NixOps.";
    };

    blobType = mkOption {
      default = "block";
      example = "page";
      type = types.str;
      description = "BLOB type: block or page.";
    };

    filePath = mkOption {
      example = "path/to/source/file";
      type = types.str;
      description = "Path to the file to upload.";
    };

    container = mkOption {
      example = "xxx-my-container";
      type = types.either types.str (resource "azure-blob-container");
      description = "The name or resource of an Azure BLOB container in which the BLOB is to be stored.";
    };

    storage = mkOption {
      default = null;
      example = "xxx-my-storage";
      type = types.nullOr (types.either types.str (resource "azure-storage"));
      description = "The name or resource of an Azure storage if the container is not managed by NixOps.";
    };

    contentEncoding = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = ''
          Specifies which content encodings have been applied to
          the blob. This value is returned to the client when the Get Blob
          (REST API) operation is performed on the blob resource. The client
          can use this value when returned to decode the blob content.
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
#          Required for page blobs. This header specifies the maximum size
#          for the page blob, up to 1 TB. The page blob size must be aligned
#          to a 512-byte boundary.
#      '';
#    };

    contentType = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = "Specifies the blob's content type.";
    };

    cacheControl = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = "The Blob service stores this value but does not use or modify it.";
    };

    metadata = mkOption {
      default = {};
      example = { loglevel = "warn"; };
      type = types.attrsOf types.str;
      description = "Metadata name/value pairs to associate with the BLOB.";
    };

  };

  config._type = "azure-blob";

}
