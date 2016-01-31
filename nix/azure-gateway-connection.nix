{ config, lib, pkgs, uuid, name, resources, ... }:

with lib;
with (import ./lib.nix lib);
{

  options = (import ./azure-mgmt-credentials.nix lib "virtual network gateway connection") // {

    name = mkOption {
      example = "my-gateway-connection";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the Azure virtual network gateway connection.";
    };

    resourceGroup = mkOption {
      example = "xxx-my-group";
      type = types.either types.str (resource "azure-resource-group");
      description = "The name or resource of an Azure resource group to create the virtual network gateway connection in.";
    };

    location = mkOption {
      example = "westus";
      type = types.str;
      description = "The Azure data center location where the virtual network gateway connection should be created.";
    };

    tags = mkOption {
      default = {};
      example = { environment = "production"; };
      type = types.attrsOf types.str;
      description = "Tag name/value pairs to associate with the virtual network gateway connection.";
    };

    virtualNetworkGateway1 = mkOption {
      default = null;
      example = "xxx-my-vnet-gateway";
      type = types.nullOr (types.either types.str (resource "azure-virtual-network-gateway"));
      description = ''
        The Azure Resource Id or NixOps resource of
        the first virtual network gateway in the connection.
      '';
    };

    virtualNetworkGateway2 = mkOption {
      default = null;
      example = "xxx-my-vnet-gateway";
      type = types.nullOr (types.either types.str (resource "azure-virtual-network-gateway"));
      description = ''
        The Azure Resource Id or NixOps resource of
        the second virtual network gateway in the connection.
      '';
    };

    localNetworkGateway2 = mkOption {
      default = null;
      example = "xxx-my-vnet-gateway";
      type = types.nullOr (types.either types.str (resource "azure-local-network-gateway"));
      description = ''
        The Azure Resource Id or NixOps resource of
        the second local network gateway in the connection.
      '';
    };

    connectionType = mkOption {
      example = "Vnet2Vnet";
      type = types.str;
      description = "The connection type of the virtual network gateway connection.";
    };

    routingWeight = mkOption {
      example = 10;
      type = types.int;
      description = "The routing weight of the virtual network gateway connection.";
    };

    sharedKey = mkOption {
      default = null;
      example = "wNEf6Vkw0Ijx2vNvdQohbZtDCaoDYqE8";
      type = types.nullOr types.str;
      description = ''
          IPSec shared key for the connection.
          Leave empty to generate automaticaly.
      '';
    };

  };

  config = {
    _type = "azure-gateway-connection";
    resourceGroup = mkDefault resources.azureResourceGroups.def-group;
  };

}
