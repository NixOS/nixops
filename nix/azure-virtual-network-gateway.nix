{ config, lib, pkgs, uuid, name, resources, ... }:

with lib;
with (import ./lib.nix lib);
{

  options = (import ./azure-mgmt-credentials.nix lib "virtual network gateway") // {

    name = mkOption {
      example = "my-virtual-network-gateway";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the Azure virtual network gateway.";
    };

    resourceGroup = mkOption {
      example = "xxx-my-group";
      type = types.either types.str (resource "azure-resource-group");
      description = "The name or resource of an Azure resource group to create the virtual network gateway in.";
    };

    location = mkOption {
      example = "westus";
      type = types.str;
      description = "The Azure data center location where the virtual network gateway should be created.";
    };

    tags = mkOption {
      default = {};
      example = { environment = "production"; };
      type = types.attrsOf types.str;
      description = "Tag name/value pairs to associate with the virtual network gateway.";
    };

    gatewaySize = mkOption {
      default = "Default";
      example = "HighPerformance";
      type = types.enum [ "Default" "HighPerformance" ];
      description = "The size of the virtual network gateway.";
    };

    gatewayType = mkOption {
      example = "RouteBased";
      type = types.str;
      description = "The type of the virtual network gateway: RouteBased or PolicyBased.";
    };

    bgpEnabled = mkOption {
      default = false;
      example = true;
      type = types.bool;
      description = "Whether BGP is enabled for this virtual network gateway or not.";
    };

    subnet.network = mkOption {
      default = null;
      example = "my-network";
      type = types.nullOr (types.either types.str (resource "azure-virtual-network"));
      description = ''
        The Azure Resource Id or NixOps resource of
        an Azure virtual network that contains the gateway subnet.
      '';
    };

    subnet.name = mkOption {
      default = "default";
      example = "my-subnet";
      type = types.str;
      description = ''
          The name of the subnet of <literal>network</literal>
          to use as the gateway subnet.
      '';
    };

  };

  config = {
    _type = "azure-virtual-network-gateway";
    resourceGroup = mkDefault resources.azureResourceGroups.def-group;
  };

}
