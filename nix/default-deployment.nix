{ lib, ... }: let
  inherit (lib) mkOption types;
in {
  options.deployment = {

    name = mkOption {
      type = types.str;
      description = ''
        The name of the NixOps deployment. This is set by NixOps.
      '';
    };

    uuid = mkOption {
      type = types.str;
      description = ''
        The UUID of the NixOps deployment. This is set by NixOps.
      '';
    };

    arguments = mkOption {
      description = ''
        Attribute set representing the NixOps arguments. This is set by NixOps.
      '';
    };
  };
}