{ config, pkgs, uuid, name, ... }:

with pkgs.lib;
with (import ./lib.nix pkgs);
{

  options = (import ./azure-credentials.nix pkgs "hosted service") // {

    name = mkOption {
      example = "my-hosted-service";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Description of the Azure hosted service. This is the <literal>Name</literal> tag of the service.";
    };

    label = mkOption {
      default = "";
      type = types.str;
      description = "Human-friendly label for the hosted service up to 100 characters in length.";
    };

    description = mkOption {
      default = "";
      type = types.str;
      description = "Description of the hosted service up to 1024 characters in length.";
    };

    location = mkOption {
      default = null;
      example = "West US";
      type = types.nullOr types.str;
      description = ''
        The Azure data center location where the hosted service should be created.
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
        Extended property name/value pairs of the hosted service. You can
        have a maximum of 50 extended property name/value pairs. The maximum
        length of the Name element is 64 characters, only alphanumeric characters
        and underscores are valid in the Name, and the name must start with a letter.
        The value has a maximum length of 255 characters.
      '';
    };

  };

  config._type = "azure-hosted-service";

}
