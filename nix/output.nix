{ pkgs, config, lib, name ? "default-output", ... }:
with lib;
{
  options = {
    name = mkOption {
      default = name;
      type = types.str;
      description = "Name of the output.";
    };

    script = mkOption {
      default = null;
      type = types.nullOr types.str;
      #type = types.nullOr (types.either types.str types.path);
      description = ''
        Text of a script which will produce a JSON value.
        <warning>Warning: This uses shell features and is potentially dangerous.</warning>
        Environment variables: 
        <envar>$out</envar> is a temp directory available for use.
        '';
    };

    value = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = "Result of running script.";
    };
  };
  config = {
    _type = "output";
  };
}
