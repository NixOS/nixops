{ config, lib, pkgs, uuid, name, resources, ... }:

with lib;
with (import ./lib.nix lib);
{

  options = (import ./azure-mgmt-credentials.nix lib "ExpressRoute circuit") // {

    name = mkOption {
      example = "my-express-route-circuit";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the Azure ExpressRoute circuit.";
    };

    resourceGroup = mkOption {
      example = "xxx-my-group";
      type = types.either types.str (resource "azure-resource-group");
      description = ''
        The name or resource of an Azure resource group
        to create the ExpressRoute circuit in.
      '';
    };

    location = mkOption {
      example = "westus";
      type = types.str;
      description = "The Azure data center location where the ExpressRoute circuit should be created.";
    };

    tags = mkOption {
      default = {};
      example = { environment = "production"; };
      type = types.attrsOf types.str;
      description = "Tag name/value pairs to associate with the ExpressRoute circuit.";
    };

    sku.tier = mkOption {
      example = "Premium";
      type = types.enum ["Standard" "Premium"];
      description = "The tier of the SKU of the ExpressRoute circuit.";
    };

    sku.family = mkOption {
      example = "UnlimitedData";
      type = types.enum ["MeteredData" "UnlimitedData"];
      description = "The family of the SKU of the ExpressRoute circuit.";
    };

    serviceProviderName = mkOption {
      example = "FakeProvider";
      type = types.str;
      description = ''
        The name of the service provider.
        This must match the provider name returned by
        "azure network express-route provider list".
      '';
    };

    peeringLocation = mkOption {
      example = "Amsterdam";
      type = types.str;
      description = ''
        Peering location for the ExpressRoute Circuit.
        This must match one of the peering locations for the chosen
        service provider from the list returned by
        "azure network express-route provider list".
      '';
    };

    bandwidth = mkOption {
      example = 100;
      type = types.int;
      description = ''
        Value of ExpressRoute circuit bandwidth in Mbps.
        This must match one of the bandwidths offered for the
        chosen service provider from the list returned by
        "azure network express-route provider list".
      '';
    };

    peerings = mkOption {
      default = {};
      example = {
        AzurePublicPeering = {
          peeringType = "AzurePublicPeering";
          peerASN = 100;
          primaryPeerAddressPrefix = "192.168.1.0/30";
          secondaryPeerAddressPrefix = "192.168.2.0/30";
          vlanId = 200;
        };
      };
      type = types.attrsOf types.attrs;
      description = ''
        Attribute set of BGP peering properties.
        The property list and allowed values deepend on the peering type.
        See Azure ExpressRoute documentation for more info.
      '';
    };

  };

  config = {
    _type = "azure-express-route-circuit";
    resourceGroup = mkDefault resources.azureResourceGroups.def-group;
  };

}
