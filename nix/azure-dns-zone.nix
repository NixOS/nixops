{ config, lib, pkgs, uuid, name, resources, ... }:

with lib;
with (import ./lib.nix lib);

{

  options = (import ./azure-mgmt-credentials.nix lib "DNS zone") // {

    name = mkOption {
      example = "test.com";
      type = types.str;
      description = "Name of the Azure DNS zone.";
    };

    resourceGroup = mkOption {
      example = "xxx-my-group";
      type = types.either types.str (resource "azure-resource-group");
      description = ''
        The name or resource of an Azure resource group
        to create the DNS zone in.
      '';
    };

    tags = mkOption {
      default = {};
      example = { environment = "production"; };
      type = types.attrsOf types.str;
      description = "Tag name/value pairs to associate with the DNS zone.";
    };

  };

  config = {
    _type = "azure-dns-zone";
    resourceGroup = mkDefault resources.azureResourceGroups.def-group;
  };

}
