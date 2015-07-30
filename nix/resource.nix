{ config, lib, name, ... }:

with lib;

{

  options = {

    # Pass-through of the resource name.
    _name = mkOption {
      default = name;
      visible = false;
      description = "Name of the resource.";
    };

    # Type of the resource (for dynamic type checks).
    _type = mkOption {
      default = "unknown";
      visible = false;
      description = "Type of the resource.";
    };

    deployment.name = mkOption {
      type = types.str;
      description = ''
        The name of the NixOps deployment. This is set by NixOps.
      '';
    };

    deployment.uuid = mkOption {
      type = types.str;
      description = ''
        The UUID of the NixOps deployment. This is set by NixOps.
      '';
    };

    deployment.arguments = mkOption {
      description = ''
        Attribute set representing the NixOps arguments. This is set by NixOps.
      '';
    };

  };

}

