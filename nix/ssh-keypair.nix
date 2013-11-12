{ config, pkgs, uuid, name, ... }:

with pkgs.lib;

{

  options = {

    publicKey = mkOption {
      default = "";
      type = types.uniq types.string;
      description = "The generated public SSH key.";
    };

    privateKey = mkOption {
      default = "";
      type = types.uniq types.string;
      description = "The generated private key.";
    };

  };

}
