{ config, pkgs, uuid, name, ... }:

with pkgs.lib;

{

  options = {

    name = mkOption {
      example = "my-health-check";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Description of the GCE HTTP Health Check. This is the <literal>Name</literal> tag of the health check.";
    };

    description = mkOption {
      default = null;
      example = "health check for databases";
      type = types.nullOr types.str;
      description = "An optional textual description of the HTTP Health Check.";
    };

    host = mkOption {
      default = null;
      example = "healthcheckhost.org";
      type = types.nullOr types.str;
      description = ''
        The value of the host header in the HTTP health check request.
        If left unset(default value), the public IP on behalf of which
        this health check is performed will be used.
      '';
    };

    path = mkOption {
      default = "/";
      example = "/is_healthy";
      type = types.str;
      description = "The request path of the HTTP health check request.";
    };

    port = mkOption {
      default = 80;
      example = 8080;
      type = types.int;
      description = "The TCP port number for the HTTP health check request.";
    };

    checkInterval = mkOption {
      default = 5;
      example = 20;
      type = types.int;
      description = "How often (in seconds) to send a health check.";
    };

    timeout = mkOption {
      default = 5;
      example = 20;
      type = types.int;
      description = "How long (in seconds) to wait before claiming failure.";
    };

    unhealthyThreshold = mkOption {
      default = 2;
      example = 4;
      type = types.int;
      description = "A so-far healthy VM will be marked unhealthy after this many consecutive failures.";
    };

    healthyThreshold = mkOption {
      default = 2;
      example = 4;
      type = types.int;
      description = "An unhealthy VM will be marked healthy after this many consecutive successes.";
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
        The GCE project which should own the HTTP Health Check. If left empty, it defaults to the
        contents of the environment variable <envar>GCE_PROJECT</envar>.
      '';
    };

  };

  config._type = "gce-http-health-check";

}
