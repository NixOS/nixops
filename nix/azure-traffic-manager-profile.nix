{ config, lib, pkgs, uuid, name, resources, ... }:

with lib;
with (import ./lib.nix lib);
let

  endpointOptions = { config, ... }: {

    options = {

      target = mkOption {
        example = "myendpoint.sample.org";
        type = types.str;
        description = ''
          The fully-qualified DNS name of the endpoint.
          Traffic Manager returns this value in DNS responses
          to direct traffic to this endpoint.
        '';
      };

      enable = mkOption {
        default = true;
        example = false;
        type = types.bool;
        description = ''
          Whether to enable the endpoint.
          If the endpoint is Enabled, it is probed for endpoint
          health and is included in the traffic routing method.
        '';
      };

      weight = mkOption {
        default = null;
        example = 1000;
        type = types.nullOr types.int;
        description = ''
          Specifies the weight assigned by Traffic Manager to the endpoint.
          This is only used if the Traffic Manager profile is configured
          to use the 'weighted' traffic routing method.
          Possible values are from 1 to 1000.
        '';
      };

      priority = mkOption {
        default = null;
        example = 1000;
        type = types.nullOr types.int;
        description = ''
          Specifies the priority of this endpoint when using the 'priority' traffic routing method.
          Priority must lie in the range 1...1000. Lower values represent higher priority.
          No two endpoints can share the same priority value.
        '';
      };

      location = mkOption {
        default = null;
        example = "westus";
        type = types.nullOr types.str;
        description = ''
          Specifies the location of the endpoint.
          Must be specified for endpoints when using the 'Performance' traffic routing method.
        '';
      };

    };
    config = {};
  };


in
{

  options = (import ./azure-mgmt-credentials.nix lib "traffic manager profile") // {

    name = mkOption {
      example = "my-traffic-manager-profile";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the Azure Traffic Manager profile.";
    };

    resourceGroup = mkOption {
      example = "xxx-my-group";
      type = types.either types.str (resource "azure-resource-group");
      description = ''
        The name or resource of an Azure resource group
        to create the Traffic Manager profile in.
      '';
    };

    tags = mkOption {
      default = {};
      example = { environment = "production"; };
      type = types.attrsOf types.str;
      description = "Tag name/value pairs to associate with the Traffic Manager profile.";
    };

    enable = mkOption {
      default = true;
      example = false;
      type = types.bool;
      description = "Whether to enable the Traffic Manager profile.";
    };

    trafficRoutingMethod = mkOption {
      default = "Performance";
      example = "Priority";
      type = types.enum [ "Performance" "Weighted" "Priority" ];
      description = ''
        Specifies the traffic routing method, used to determine
        which endpoint is returned in response to incoming DNS queries.
      '';
    };

    dns.relativeName = mkOption {
      example = "myservice";
      type = types.str;
      description = ''
        Specifies the relative DNS name provided by this Traffic Manager profile.
        This value is combined with the DNS domain name used by Azure Traffic Manager
        to form the fully-qualified domain name (FQDN) of the profile.
      '';
    };

    dns.ttl = mkOption {
      example = 30;
      type = types.int;
      description = ''
        Specifies the DNS Time-to-Live (TTL), in seconds.
        This informs the Local DNS resolvers and DNS clients
        how long to cache DNS responses provided by this Traffic Manager profile.
        Possible values are 30...999,999.
      '';
    };

    monitor.protocol = mkOption {
      default = "HTTP";
      example = "HTTPS";
      type = types.enum [ "HTTP" "HTTPS" ];
      description = "Specifies the protocol to use to monitor endpoint health.";
    };

    monitor.port = mkOption {
      default = 80;
      example = 8080;
      type = types.int;
      description = "Specifies the TCP port used to monitor endpoint health. Possible values are 1...65535";
    };

    monitor.path = mkOption {
      default = "/";
      example = "/alive";
      type = types.str;
      description = "Specifies the path relative to the endpoint domain name used to probe for endpoint health.";
    };

    endpoints = mkOption {
      default = {};
      example = {
        west_us_endpoint = {
          target = "westus.sample.org";
          location = "westus";
        };
      };
      type = with types; attrsOf (submodule endpointOptions);
      description = "An attribute set of endpoints";
    };

  };

  config = {
    _type = "azure-traffic-manager-profile";
    resourceGroup = mkDefault resources.azureResourceGroups.def-group;
  };

}
