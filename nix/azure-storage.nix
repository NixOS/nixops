{ config, pkgs, uuid, name, ... }:

with pkgs.lib;
with (import ./lib.nix pkgs);
{

  options = (import ./azure-credentials.nix pkgs "storage") // {

    name = mkOption {
      example = "my-hosted-service";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Description of the Azure storage account. This is the <literal>Name</literal> tag of the storage account.";
    };

    label = mkOption {
      default = "";
      type = types.str;
      description = "Human-friendly label for the storage up to 100 characters in length.";
    };

    description = mkOption {
      default = "";
      type = types.str;
      description = "Description of the storage up to 1024 characters in length.";
    };

    location = mkOption {
      default = null;
      example = "West US";
      type = types.nullOr types.str;
      description = ''
        The Azure data center location where the storage should be created.
        You can specify either a location or affinity group, but not both.
      '';
    };

    affinityGroup = mkOption {
      default = null;
      example = "xxx-my-affinity-group";
      type = types.nullOr ( types.either types.str (resource "azure-affinity-group") );
      description = ''
        The name or resource of an existing affinity group. You can specify either
        a location or affinity group, but not both.
      '';
    };

    extendedProperties = mkOption {
      default = {};
      example = { loglevel = "warn"; };
      type = types.attrsOf types.str;
      description = ''
        Extended property name/value pairs of the storage. You can
        have a maximum of 50 extended property name/value pairs. The maximum
        length of the Name element is 64 characters, only alphanumeric characters
        and underscores are valid in the Name, and the name must start with a letter.
        The value has a maximum length of 255 characters.
      '';
    };

    accountType = mkOption {
      default = "Standard_LRS";
      type = types.str;
      description = ''
        Specifies whether the account supports locally-redundant storage,
        geo-redundant storage, zone-redundant storage, or read access
        geo-redundant storage.
        Possible values are: Standard_LRS, Standard_ZRS, Standard_GRS, Standard_RAGRS
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
  };

  config._type = "azure-storage";

}
