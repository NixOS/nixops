{ config, lib, pkgs, uuid, name, ... }:

with lib;
with import ./lib.nix lib;
{

  options = (import ./gce-credentials.nix pkgs "HTTP health check") // {

    name = mkOption {
      example = "my-health-check";
      default = "n-${shorten_uuid uuid}-${name}";
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

  };

  config._type = "gce-http-health-check";

}
