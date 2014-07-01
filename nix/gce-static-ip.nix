{ config, pkgs, uuid, name, ... }:

with pkgs.lib;

{

  options = {

    name = mkOption {
      example = "my-public-ip";
      default = "nixops-${uuid}-${name}";
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

    serviceAccount = mkOption {
      default = "";
      example = "12345-asdf@developer.gserviceaccount.com";
      type = types.str;
      description = ''
        The GCE Service Account Email. If left empty, it defaults to the
        contents of the environment variable <envar>GCE_SERVICE_ACCOUNT</envar>.
      '';
    };

    accessKey = mkOption {
      default = "";
      example = "/path/to/secret/key.pem";
      type = types.str;
      description = ''
        The path to GCE Service Account key. If left empty, it defaults to the
        contents of the environment variable <envar>ACCESS_KEY_PATH</envar>.
      '';
    };

    project = mkOption {
      default = "";
      example = "myproject";
      type = types.str;
      description = ''
        The GCE project which should own the IP address. If left empty, it defaults to the
        contents of the environment variable <envar>GCE_PROJECT</envar>.
      '';
    };

  };

  config._type = "gce-static-ip";

}
