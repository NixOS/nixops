{ config, pkgs, uuid, name, ... }:

with pkgs.lib;

{

  options = {

    public_key = mkOption {
      default = "";
      type = types.uniq types.string;
      description = "The generated public SSH key.";
    };

    private_key = mkOption {
      default = "";
      type = types.uniq types.string;
      description = "The generated private key.";
    };

  };

}
