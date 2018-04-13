{ lib } :

with lib;
{
  options = {

    source = mkOption {
      type = types.str;
      default = "default";
      description = ''
      '';
    };

    type = mkOption {
      type = types.enum [ "bridge" "virtual" ];
      default = "virtual";
      description = ''
      '';
    };

  };

}
