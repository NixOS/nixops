{ config, lib, uuid, name, ... }:

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
