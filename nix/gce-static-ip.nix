{ config, lib, pkgs, uuid, name, ... }:

with lib;
with import ./lib.nix lib;

{

  options = (import ./gce-credentials.nix pkgs "IP address") // {

    name = mkOption {
      example = "my-public-ip";
      default = "n-${shorten_uuid uuid}-${name}";
      type = types.str;
      description = "Description of the GCE static IP address. This is the <literal>Name</literal> tag of the address.";
    };

    region = mkOption {
      example = "europe-west1";
      type = types.str;
      description = "The GCE region to which the IP address should be bound.";
    };

    ipAddress = mkOption {
      default = null;
      example = "123.123.123.123";
      type = types.nullOr types.str;
      description = ''
        The specific ephemeral IP address to promote to a static one.

        This lets you permanently reserve an ephemeral address used
        by one of resources to preserve it across machine teardowns
        or reassign it to another resource. Changing value of, setting
        or unsetting this option has no effect once the address resource
        is deployed, thus you can't lose the static IP unless you
        explicitly destroy it.
      '';
    };

  };

  config._type = "gce-static-ip";

}
