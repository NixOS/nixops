{ config, pkgs, uuid, name, ... }:

with pkgs.lib;
with (import ./lib.nix pkgs);
let

  machine = mkOptionType {
    name = "GCE machine";
    check = x: x ? gce;
    merge = mergeOneOption;
  };

in
{

  options = (import ./gce-credentials.nix pkgs "target pool") // {

    name = mkOption {
      example = "my-target-pool";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Description of the GCE Target Pool. This is the <literal>Name</literal> tag of the target pool.";
    };

    region = mkOption {
      example = "europe-west1";
      type = types.str;
      description = "The GCE region to where the GCE Target Pool instances should reside.";
    };

    healthCheck = mkOption {
      default = null;
      example = "resources.gceHTTPHealthChecks.my-check";
      type = types.nullOr (union types.str (resource "gce-http-health-check"));
      description = ''
        GCE HTTP Health Check resource or name of a HTTP Health Check resource not managed by NixOps.

        A member VM in this pool is considered healthy if and only if the
        specified health checks passes. Unset health check means all member
        virtual machines will be considered healthy at all times but the health
        status of this target pool will be marked as unhealthy to indicate that
        no health checks are being performed.
      '';
    };

    machines = mkOption {
      default = [];
      example = [ "machines.httpserver1" "machines.httpserver2" ];
      type = types.listOf (union types.str machine);
      description = ''
        The list of machine resources or fully-qualified GCE Node URLs to add to this pool.
      '';
    };

  };

  config._type = "gce-target-pool";

}
