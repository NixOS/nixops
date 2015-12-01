{ config, lib, pkgs, uuid, name, ... }:

with lib;
with (import ./lib.nix lib);
{

  options = (import ./azure-credentials.nix lib "affinity group") // {

    name = mkOption {
      example = "my-affinity-group";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Description of the Azure affinity group. This is the <literal>Name</literal> tag of the affinity group.";
    };

    location = mkOption {
      example = "West US";
      type = types.str;
      description = "The Azure data center location where the affinity group should be created.";
    };

    label = mkOption {
      default = "";
      type = types.str;
      description = "Human-friendly label for the affinity group up to 100 characters in length.";
    };

    description = mkOption {
      default = "";
      type = types.str;
      description = "Description for the affinity group up to 1024 characters in length.";
    };

  };

  config._type = "azure-affinity-group";

}
