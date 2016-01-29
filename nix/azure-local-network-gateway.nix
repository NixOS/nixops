{ config, lib, pkgs, uuid, name, resources, ... }:

with lib;
with (import ./lib.nix lib);
{

  options = (import ./azure-mgmt-credentials.nix lib "local network gateway") // {

    name = mkOption {
      example = "my-local-network-gateway";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the Azure local network gateway.";
    };

    resourceGroup = mkOption {
      example = "xxx-my-group";
      type = types.either types.str (resource "azure-resource-group");
      description = "The name or resource of an Azure resource group to create the local network gateway in.";
    };

    location = mkOption {
      example = "westus";
      type = types.str;
      description = "The Azure data center location where the local network gateway should be created.";
    };

    tags = mkOption {
      default = {};
      example = { environment = "production"; };
      type = types.attrsOf types.str;
      description = "Tag name/value pairs to associate with the local network gateway.";
    };

    ipAddress = mkOption {
      example = "20.20.20.20";
      type = types.str;
      description = "The public IP address of the local network gateway.";
    };

    addressSpace = mkOption {
      example = "10.1.0.0/24";
      type = types.listOf types.str;
      description = ''
        List the address prefixes in CIDR notation of the local network site.
        Traffic addressed at these prefixes will be routed to the local network site.
      '';
    };

  };

  config = {
    _type = "azure-local-network-gateway";
    resourceGroup = mkDefault resources.azureResourceGroups.def-group;
  };

}
