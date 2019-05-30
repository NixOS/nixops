{ config, lib, ... }:

with lib;

{
  options = {
    vaultToken = mkOption {
      default = "";
      type = types.str;
      description = "Vault token.";
    };

    vaultAddress = mkOption {
      default = "";
      example = "https://vault.nixops.com:8200";
      type = types.str;
      description = "Vault URL address.";
    };
  };
}