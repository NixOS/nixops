{ lib, name, ... }:

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
  };

}

