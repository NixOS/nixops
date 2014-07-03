{ config, pkgs, uuid, name, ... }:

with pkgs.lib;

{

  options = (import ./gce-credentials.nix pkgs "bucket") // {

    name = mkOption {
      example = "my-bucket";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "This is the <literal>Name</literal> tag of the bucket.";
    };

  };

  config._type = "gse-bucket";

}
