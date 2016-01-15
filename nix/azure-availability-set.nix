{ config, lib, pkgs, uuid, name, ... }:

with lib;
with (import ./lib.nix lib);
{

  options = (import ./azure-mgmt-credentials.nix lib "availability set") // {

    name = mkOption {
      default = "nixops-${uuid}-${name}";
      example = "my-availability-set";
      type = types.str;
      description = "Name of the Azure availability set.";
    };

    resourceGroup = mkOption {
      example = "xxx-my-group";
      type = types.either types.str (resource "azure-resource-group");
      description = "The name or resource of an Azure resource group to create the availability set in.";
    };

    location = mkOption {
      example = "westus";
      type = types.str;
      description = "The Azure data center location where the availability set should be created.";
    };

    tags = mkOption {
      default = {};
      example = { environment = "production"; };
      type = types.attrsOf types.str;
      description = "Tag name/value pairs to associate with the availability set.";
    };

    platformUpdateDomainCount = mkOption {
      default = 5;
      example = 10;
      type = types.int;
      description = ''
        The number of update domains that are used. Only one of the update domains
        can be rebooted or unavailable at once during planned maintenance.
        A maximum of 20 update domains can be used.
      '';
    };

    platformFaultDomainCount = mkOption {
      default = 3;
      example = 3;
      type = types.int;
      description = ''
        The number of update domains that are used. A single hardware failure
        can only affect virtual machines in one fault domain.
        A maximum of 3 fault domains can be used.
      '';
    };

  };

  config._type = "azure-availability-set";

}
