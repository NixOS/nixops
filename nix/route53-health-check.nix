{ config, lib, uuid, name, ... }:

with lib;
with (import ./lib.nix lib);

{

  options = {

    name = mkOption {
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the recordset.";
    };

    accessKeyId = mkOption {
      type = types.str;
      default = "";
      description = ''
        The AWS Access Key ID.  If left empty, it defaults to the
        contents of the environment variables
        <envar>EC2_ACCESS_KEY</envar> or
        <envar>AWS_ACCESS_KEY_ID</envar> (in that order).  The
        corresponding Secret Access Key is not specified in the
        deployment model, but looked up in the file
        <filename>~/.ec2-keys</filename>, which should specify, on
        each line, an Access Key ID followed by the corresponding
        Secret Access Key. If the lookup was unsuccessful it is continued
        in the standard AWS tools <filename>~/.aws/credentials</filename> file.
        If it does not appear in these files, the
        environment variables
        <envar>EC2_SECRET_KEY</envar> or
        <envar>AWS_SECRET_ACCESS_KEY</envar> are used.
      '';
    };

    ipAddress = mkOption {
      type = types.nullOr (types.either types.str (resource "machine"));
      apply = x: if x == null || (builtins.isString x) then x else "res-" + x._name;
      default = null;
      description = ''
        The IPv4 or IPv6 IP address of the endpoint to perform health checks on.
      '';
    };

    port = mkOption {
      type = types.nullOr types.int;
      default = null;
      description = ''
        The port on the endpoint to perform health checks on.
      '';
    };

    type = mkOption {
      type = types.enum [ "HTTP" "HTTPS" "HTTP_STR_MATCH" "HTTPS_STR_MATCH" "TCP" "CALCULATED" "CLOUDWATCH_METRIC" ];
      description = ''
        The type of health check that you want to create, which indicates how
        Route 53 determines whether an endpoint is healthy.
      '';
    };

    resourcePath = mkOption {
      type = types.str;
      default = "";
      description = ''
        The path used for performing health checks. 
      '';
    };

    fullyQualifiedDomainName = mkOption {
      type = types.str;
      default = "";
      description = ''
        See https://docs.aws.amazon.com/Route53/latest/APIReference/API_HealthCheckConfig.html
      '';
    };

    searchString = mkOption {
      type = types.str;
      default = "";
      description = ''
        The string to search for in the response body from the specified resource. If
        the string appears in the response body, Route 53 considers the resource healthy.
      '';
    };

    requestInterval = mkOption {
      type = types.enum [ 10 30 ] ;
      default = 30;
      description = ''
        Number of seconds between health checks.
      '';
    };

    failureThreshold = mkOption {
      type = types.int;
      default = 3;
      description = ''
        The number of consecutive health checks that an endpoint must pass or fail
        to change the current status of the endpoint from unhealthy to healthy or
        vice versa.
      '';
    };

    measureLatency = mkOption {
      type = types.bool;
      default = false;
      description = ''
        Whether to measure latency (metrics will be available in CloudWatch).
      '';
    };

    inverted = mkOption {
      type = types.bool;
      default = false;
      description = ''
        Whether you want to invert the status of the health check.
      '';
    };

    enableSNI = mkOption {
      type = types.bool;
      default = false;
      description = ''
        Specify whether to send the value of fullyQualifiedDomainName to the endpoint
        in the client_hello message during TLS negotiation.
      '';
    };

    regions = mkOption {
      type = types.list types.str;
      default = [];
      description = ''
        Regions to trigger health checks from. Empty list (default) enables health checks
        from all regions.
      '';
    };

    alarmIdentifier.region = mkOption {
      type = types.str;
      default = "";
      description = ''
        Region of the CloudWatch alarm that you want Amazon Route 53 health checkers to
        use to determine whether this health check is healthy.
      '';
    };

    alarmIdentifier.name = mkOption {
      type = types.str;
      default = "";
      description = ''
        Name of the CloudWatch alarm that you want Amazon Route 53 health checkers to
        use to determine whether this health check is healthy.
      '';
    };

    insufficientDataHealthStatus = mkOption {
      type = types.nullOr (types.enum [ "Healthy" "Unhealthy" "LastKnownStatus" ]);
      default = null;
      description = ''
        When CloudWatch has insufficient data about the metric to determine the alarm
        state, the status that you want Amazon Route 53 to assign to the health check.
      '';
    };

    childHealthChecks = mkOption {
      type = types.list (types.either types.str (resource "route53-health-check"));
      default = [];
      apply = l: map (x: if (builtins.isString x) then x else "res-" + x._name) l;
      description = ''
        Health checks to use for CALCULATED health check type.
      '';
    };

    healthThreshold = mkOption {
      type = types.int;
      default = builtins.length config.childHealthChecks;
      description = ''
        The number of child health checks for the CALCULATED health check
        to be considered healthy. Defaults to number of health checks in
        childHealthChecks option.
      '';
    };
  };

  config = {
    _type = "route53-health-check";
  };
}
