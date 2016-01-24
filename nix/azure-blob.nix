{ config, lib, pkgs, uuid, name, ... }:

with lib;
with (import ./lib.nix lib);
{

  options = {

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
      default = "BlockBlob";
      example = "PageBlob";
      type = types.enum [ "BlockBlob" "PageBlob" ];
      description = "BLOB type: BlockBlob or PageBlob.";
    };

    filePath = mkOption {
      default = null;
      example = "path/to/source/file";
      type = types.nullOr types.str;
      description = "Path to the local file to upload.";
    };

    copyFromBlob = mkOption {
      default = null;
      example = "https://myaccount.blob.core.windows.net/mycontainer/myblob";
      type = types.nullOr types.str;
      description = ''
        Create the BLOB by copying the contents of an existing one.
        Any BLOB in your subscription or a publicly-accessible BLOB
        in another subscription can be copied.
      '';
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
      description = "The MIME content type of the BLOB. ";
    };

    cacheControl = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = "The Blob service stores this value but does not use or modify it.";
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
      description = "Metadata name/value pairs to associate with the BLOB.";
    };

  };

  config._type = "azure-blob";

}
