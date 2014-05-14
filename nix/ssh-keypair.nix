{ config, pkgs, uuid, name, lib ? pkgs.lib, ... }:

with lib;

{

  options = {

    publicKey = mkOption {
      default = "";
      type = types.str;
      description = "The generated public SSH key.";
    };

    privateKey = mkOption {
      default = "";
      type = types.str;
      description = "The generated private key.";
    };

  };

}
