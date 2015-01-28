{ config, pkgs, uuid, name, ... }:

with pkgs.lib;
with (import ./lib.nix pkgs);
{

  options = (import ./azure-credentials.nix pkgs "reserved IP address") // {

    name = mkOption {
      example = "my-public-ip";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Description of the Azure reserved IP address. This is the <literal>Name</literal> tag of the address.";
    };

    location = mkOption {
      example = "West US";
      type = types.str;
      description = ''
        The Azure data center where the reserved IP address should be located.
        This should be the same location that is assigned to the cloud service
        containing the deployment that will use the reserved IP address.
      '';
    };

    label = mkOption {
      default = "";
      type = types.str;
      description = "Human-friendly label for the reserved IP address up to 100 characters in length.";
    };

  };

  config._type = "azure-reserved-ip-address";

}
