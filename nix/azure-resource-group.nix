{ config, lib, pkgs, uuid, name, ... }:

with lib;
with (import ./lib.nix lib);
{

  options = (import ./azure-mgmt-credentials.nix lib "resource group") // {

    name = mkOption {
      example = "my-resource-group";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Description of the Azure Resource Group. This is the <literal>Name</literal> tag of the group.";
    };

    location = mkOption {
      example = "westus";
      type = types.str;
      description = "The Azure data center location where the resource group should be created.";
    };

    tags = mkOption {
      default = {};
      example = { environment = "production"; };
      type = types.attrsOf types.str;
      description = "Tag name/value pairs to associate with the resource group.";
    };

  };

  config._type = "azure-resource-group";

}
