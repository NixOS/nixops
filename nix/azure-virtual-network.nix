{ config, lib, pkgs, uuid, name, resources, ... }:

with lib;
with (import ./lib.nix lib);
{

  options = (import ./azure-mgmt-credentials.nix lib "virtual network") // {

    name = mkOption {
      default = "nixops-${uuid}-${name}";
      example = "my-network";
      type = types.str;
      description = "Name of the Azure virtual network.";
    };

    resourceGroup = mkOption {
      example = "xxx-my-group";
      type = types.either types.str (resource "azure-resource-group");
      description = "The name or resource of an Azure resource group to create the network in.";
    };

    location = mkOption {
      example = "westus";
      type = types.str;
      description = "The Azure data center location where the virtual network should be created.";
    };

    addressSpace = mkOption {
      example = [ "10.1.0.0/16" "10.3.0.0/16" ];
      type = types.listOf types.str;
      description = "The list of address blocks reserved for this virtual network in CIDR notation.";
    };

    tags = mkOption {
      default = {};
      example = { environment = "production"; };
      type = types.attrsOf types.str;
      description = "Tag name/value pairs to associate with the virtual network.";
    };

    dnsServers = mkOption {
      default = [];
      example = [ "8.8.8.8" "8.8.4.4" ];
      type = types.nullOr (types.listOf types.str);
      description = ''
        List of DNS servers IP addresses to provide via DHCP.
        Leave empty to provide the default Azure DNS servers.
      '';
    };
  };

  config = {
    _type = "azure-virtual-network";
    resourceGroup = mkDefault resources.azureResourceGroups.def-group;
  };

}
