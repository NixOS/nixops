{ pkgs, config, lib, name ? "default-output", ... }:
with lib;
{
  options = {
    name = mkOption {
      default = name;
      type = types.str;
      description = "Name of the Command Output.";
    };

    script = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = ''
        Text of a script which will produce a JSON value.
        Warning: This uses shell features and is potentially dangerous.
        Environment variables:
        ``$out`` is a temp directory available for use.
        '';
    };

    value = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = "Result of running script.";
    };
  };
  config = {
    _type = "commandOutput";
  };
}
