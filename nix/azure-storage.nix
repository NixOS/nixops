{ config, lib, pkgs, uuid, name, ... }:

with lib;
with (import ./lib.nix lib);
let

  retention_policy_options = { enable ? false }: {
    enable = mkOption {
      default = enable;
      example = true;
      type = types.bool;
      description = "Whether a retention policy is enabled for the service.";
    };

    days = mkOption {
      default = 7;
      example = 3;
      type = types.int;
      description = ''
        Indicates the number of days that metrics or logging data is retained.
        All data older than this value will be deleted.
      '';
    };
  };

  metrics_options = { enable ? false }: {
    enable = mkOption {
      default = enable;
      example = true;
      type = types.bool;
      description = "Whether metrics are enabled for the service.";
    };

    includeAPIs = mkOption {
      default = enable;
      example = true;
      type = types.bool;
      description = ''
        Whether metrics should generate summary statistics
        for called API operations.
      '';
    };

    retentionPolicy = retention_policy_options { inherit enable; };
  };

  logging_options = {
    delete = mkOption {
      default = false;
      example = true;
      type = types.bool;
      description = "Whether delete requests should be logged.";
    };

    read = mkOption {
      default = false;
      example = true;
      type = types.bool;
      description = "Whether read requests should be logged.";
    };

    write = mkOption {
      default = false;
      example = true;
      type = types.bool;
      description = "Whether write requests should be logged.";
    };

    retentionPolicy = retention_policy_options {};
  };

  service_options = {
    logging = logging_options;
    hourMetrics = metrics_options { enable = true; };
    minuteMetrics = metrics_options {};
  };

in
{

  options = (import ./azure-mgmt-credentials.nix lib "storage") // {

    name = mkOption {
      example = "my-storage";
      type = types.str;
      description = ''
        Name of the Azure storage account.
        Must be globally-unique, between 3 and 24 characters in length,
        and must consist of numbers and lower-case letters only.
      '';
    };

    resourceGroup = mkOption {
      example = "xxx-my-group";
      type = types.either types.str (resource "azure-resource-group");
      description = "The name or resource of an Azure resource group to create the storage in.";
    };

    location = mkOption {
      example = "westus";
      type = types.str;
      description = "The Azure data center location where the storage should be created.";
    };

    customDomain = mkOption {
      default = "";
      example = "mydomain.org";
      type = types.str;
      description = "User domain assigned to the storage account. Name is the CNAME source.";
    };

    accountType = mkOption {
      default = "Standard_LRS";
      type = types.str;
      description = ''
        Specifies whether the account supports locally-redundant storage,
        geo-redundant storage, zone-redundant storage, or read access
        geo-redundant storage.
        Possible values are: Standard_LRS, Standard_ZRS, Standard_GRS, Standard_RAGRS, Premium_LRS
      '';
    };

    activeKey = mkOption {
      default = "primary";
      type = types.str;
      description = ''
        Specifies which of the access keys should be used by containers, tables and queues.
        The keys provide the same access, but can be independently regenerated which allows
        seamless key replacement.
        Possible values are: primary, secondary.
      '';
    };

    tags = mkOption {
      default = {};
      example = { environment = "production"; };
      type = types.attrsOf types.str;
      description = "Tag name/value pairs to associate with the storage.";
    };

    blobService = service_options;
    queueService = service_options;
    tableService = service_options;
  };

  config._type = "azure-storage";

}
