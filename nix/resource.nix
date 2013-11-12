{ config, pkgs, uuid, name, ... }:

with pkgs.lib;

{

  options = {

    # Pass-through of the resource name.
    _name = mkOption {
      default = name;
      visible = false;
      description = "Name of the resource.";
    };

  };

}

