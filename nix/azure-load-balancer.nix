{ config, lib, pkgs, uuid, name, resources, ... }:

with lib;
with (import ./lib.nix lib);
let

  lbRuleOptions = { config, ... }: {
    options = {

      frontendInterface = mkOption {
        default = "default";
        example = "webservers";
        type = types.str;
        description = "The name of a frontend interface over which this Load Balancing Rule operates.";
      };

      backendAddressPool = mkOption {
        default = "default";
        example = "webservers";
        type = types.str;
        description = "The name of a backend address pool over which this Load Balancing Rule operates.";
      };

      probe = mkOption {
        default = null;
        example = "webservers";
        type = types.nullOr types.str;
        description = "The name of a probe used by this Load Balancing Rule.";
      };

      protocol = mkOption {
        default = "Tcp";
        example = "Udp";
        type = types.str;
        description = "The transport protocol for the external endpoint. Possible values are Udp or Tcp.";
      };

      frontendPort = mkOption {
        example = 80;
        type = types.int;
        description = ''
            The port for the external endpoint.
            Port numbers for each Rule must be unique within the Load Balancer.
            Possible values range between 1 and 65535, inclusive.
        '';
      };

      backendPort = mkOption {
        example = 80;
        type = types.int;
        description = ''
            The port used for internal connections on the endpoint.
            Possible values range between 1 and 65535, inclusive.
        '';
      };

      enableFloatingIp = mkOption {
        default = false;
        example = true;
        type = types.bool;
        description = ''
            Floating IP is pertinent to failover scenarios:
            a "floating" IP is reassigned to a secondary server
            in case the primary server fails.
            Floating IP is required for SQL AlwaysOn.
        '';
      };

      idleTimeout = mkOption {
        default = 4;
        example = 30;
        type = types.int;
        description = ''
          Specifies the timeout in minutes for the Tcp idle connection.
          The value can be set between 4 and 30 minutes.
          This property is only used when the protocol is set to <literal>Tcp</literal>.
        '';
      };

      loadDistribution = mkOption {
        default = "Default";
        example = "SourceIP";
        type = types.str;
        description = ''
            Specifies the load balancing distribution type to be used by the Load Balancer Rule.
            Possible values are: Default - The load balancer is configured to use a 5 tuple hash
            to map traffic to available servers; SourceIP - The load balancer is configured to
            use a 2 tuple hash to map traffic to available servers; SourceIPProtocol - The load
            balancer is configured to use a 3 tuple hash to map traffic to available servers.
        '';
      };

    };
    config = {};
  };


  probeOptions = { config, ... }: {
    options = {

      protocol = mkOption {
        default = "Tcp";
        example = "Http";
        type = types.str;
        description = ''
          Specifies the protocol of the probe request.
          Possible values are Http or Tcp. If Tcp is specified, a received ACK is required for
          the probe to be successful. If Http is specified, a 200 OK response from the specified
          URI is required for the probe to be successful.
        '';
      };

      port = mkOption {
        example = 80;
        type = types.int;
        description = ''
          Port on which the Probe queries the backend endpoint.
          Possible values range from 1 to 65535, inclusive.
        '';
      };

      path = mkOption {
        default = null;
        example = "/is-up";
        type = types.nullOr types.str;
        description = ''
          The URI used for requesting health status from the backend endpoint.
          Used if protocol is set to http.
        '';
      };

      interval = mkOption {
        default = 15;
        example = 5;
        type = types.int;
        description = ''
            The interval, in seconds, between probes to the backend endpoint for health status.
            The minimum allowed value is 5.
        '';
      };

      numberOfProbes = mkOption {
        default = 2;
        example = 5;
        type = types.int;
        description = ''
            The number of failed probe attempts after which the backend endpoint
            is removed from rotation. The default value is 2. NumberOfProbes
            multiplied by interval value must be greater or equal to 10.
            Endpoints are returned to rotation when at least one probe is successful.
        '';
      };

    };
    config = {};
  };


  frontendInterfaceOptions = { config, ... }: {
    options = {

      subnet.network = mkOption {
        default = null;
        example = "my-network";
        type = types.nullOr (types.either types.str (resource "azure-virtual-network"));
        description = ''
          The Azure Resource Id or NixOps resource of
          an Azure virtual network that contains the subnet.
        '';
      };

      subnet.name = mkOption {
        default = "default";
        example = "my-subnet";
        type = types.str;
        description = ''
            The name of the subnet of <literal>network</literal>
            in which to obtain the private IP address.
        '';
      };

      privateIpAddress = mkOption {
        default = null;
        example = "10.10.10.10";
        type = types.nullOr types.str;
        description = ''
            The static private IP address to reserve for the load balancer frontend interface.
            The address must be in the address space of <literal>subnet</literal>.
            Leave empty to auto-assign.
        '';
      };

      publicIpAdress = mkOption {
        default = null;
        example = "my-reserved-ip";
        type = types.nullOr (types.either types.str (resource "azure-reserved-ip-address"));
        description = ''
          The Azure Resource Id or NixOps resource of
          an Azure reserved IP address resource to use for the frontend interface.
          Leave empty to create an internal load balancer interface.
        '';
      };

    };
    config = {};
  };

  natRuleOptions = { config, ... }: {
    options = {

      frontendInterface = mkOption {
        default = "default";
        example = "webservers";
        type = types.str;
        description = "The name of a frontend interface over which this Inbound NAT Rule operates.";
      };

      protocol = mkOption {
        default = "Tcp";
        example = "Udp";
        type = types.str;
        description = "The transport protocol for the external endpoint. Possible values are Udp or Tcp.";
      };

      frontendPort = mkOption {
        example = 80;
        type = types.int;
        description = ''
            The port for the external endpoint.
            Port numbers for each Rule must be unique within the Load Balancer.
            Possible values range between 1 and 65535, inclusive.
        '';
      };

      backendPort = mkOption {
        example = 80;
        type = types.int;
        description = ''
            The port used for internal connections on the endpoint.
            Possible values range between 1 and 65535, inclusive.
        '';
      };

      enableFloatingIp = mkOption {
        default = false;
        example = true;
        type = types.bool;
        description = ''
            Floating IP is pertinent to failover scenarios:
            a "floating" IP is reassigned to a secondary server
            in case the primary server fails.
            Floating IP is required for SQL AlwaysOn.
        '';
      };

      idleTimeout = mkOption {
        default = 4;
        example = 30;
        type = types.int;
        description = ''
          Specifies the timeout in minutes for the Tcp idle connection.
          The value can be set between 4 and 30 minutes.
          This property is only used when the protocol is set to <literal>Tcp</literal>.
        '';
      };

    };
    config = {};
  };

in
{

  options = (import ./azure-mgmt-credentials.nix lib "load balancer") // {

    name = mkOption {
      default = "nixops-${uuid}-${name}";
      example = "my-network";
      type = types.str;
      description = "Name of the Azure load balancer.";
    };

    resourceGroup = mkOption {
      example = "xxx-my-group";
      type = types.either types.str (resource "azure-resource-group");
      description = "The name or resource of an Azure resource group to create the load balancer in.";
    };

    location = mkOption {
      example = "westus";
      type = types.str;
      description = "The Azure data center location where the load balancer should be created.";
    };

    tags = mkOption {
      default = {};
      example = { environment = "production"; };
      type = types.attrsOf types.str;
      description = "Tag name/value pairs to associate with the load balancer.";
    };

    backendAddressPools = mkOption {
      default = [ "default" ];
      example = [ "website" "db" ];
      type = types.listOf types.str;
      description = "The list of names of backend address pools to create";
    };

    frontendInterfaces = mkOption {
      default = {};
      example = {
        default = {
          subnet.network = "my-virtual-network";
          publicIpAdress = "my-reserved-address";
        };
      };
      type = types.attrsOf types.optionSet;
      options = frontendInterfaceOptions;
      description = "An attribute set of frontend network interfaces.";
    };

    loadBalancingRules = mkOption {
      default = {};
      example = {
        website = {
          frontendPort = 80;
          backendPort = 8080;
          probe = "web";
        };
      };
      type = types.attrsOf types.optionSet;
      options = lbRuleOptions;
      description = "An attribute set of load balancer rules.";
    };

    inboundNatRules = mkOption {
      default = {};
      example = {
        admin-ssh = {
          frontendPort = 2201;
          backendPort = 22;
        };
      };
      type = types.attrsOf types.optionSet;
      options = natRuleOptions;
      description = "An attribute set of inbound NAT rules.";
    };

    probes = mkOption {
      default = {};
      example = {
        web = {
          protocol = "http";
          port = 8080;
          path = "/is-alive";
        };
      };
      type = types.attrsOf types.optionSet;
      options = probeOptions;
      description = "An attribute set of load balancer probes";
    };

  };

  config = {
    _type = "azure-load-balancer";
    resourceGroup = mkDefault resources.azureResourceGroups.def-group;
  };

}
