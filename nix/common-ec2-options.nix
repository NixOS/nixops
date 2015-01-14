{ lib }:

with lib;

{

  tags = mkOption {
      default = { };
      example = { foo = "bar"; xyzzy = "bla"; };
      type = types.attrsOf types.str;
      description = ''
        Tags assigned to the instance.  Each tag name can be at most
        128 characters, and each tag value can be at most 256
        characters.  There can be at most 10 tags.
      '';
  };

}
