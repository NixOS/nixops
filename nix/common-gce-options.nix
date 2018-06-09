{ lib }:

with lib;

{

  labels = mkOption {
      default = { };
      example = { foo = "bar"; xyzzy = "bla"; };
      type = types.attrsOf types.str;
      description = ''
        A set of key/value label pairs to assign to the instance.
      '';
  };

}
