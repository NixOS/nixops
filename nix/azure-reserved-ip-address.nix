{ config, lib, pkgs, uuid, name, ... }:

with lib;
with (import ./lib.nix lib);
{

  options = (import ./azure-mgmt-credentials.nix lib "reserved IP address") // {

    name = mkOption {
      example = "my-public-ip";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Description of the Azure reserved IP address. This is the <literal>Name</literal> tag of the address.";
    };

    resourceGroup = mkOption {
      example = "xxx-my-group";
      type = types.either types.str (resource "azure-resource-group");
      description = "The name or resource of an Azure resource group to create the IP address in.";
    };

    location = mkOption {
      example = "West US";
      type = types.str;
      description = "The Azure data center where the reserved IP address should be located.";
    };

    tags = mkOption {
      default = {};
      example = { environment = "production"; };
      type = types.attrsOf types.str;
      description = "Tag name/value pairs to associate with the IP address.";
    };

    idleTimeout = mkOption {
      default = 4;
      example = 30;
      type = types.int;
      description = ''
          The timeout for the TCP idle connection.
          The value can be set between 4 and 30 minutes.
      '';
    };

    domainNameLabel = mkOption {
      default = null;
      example = "mylabel";
      type = types.nullOr types.str;
      description = ''
          The concatenation of the domain name label and the regionalized DNS
          zone make up the fully qualified domain name associated with the
          public IP address. If a domain name label is specified, an A DNS
          record is created for the public IP in the Microsoft Azure DNS
          system. Example FQDN: mylabel.northus.cloudapp.azure.com.
      '';
    };

    reverseFqdn = mkOption {
      default = null;
      example = "mydomain.com";
      type = types.nullOr types.str;
      description = ''
          A fully qualified domain name that resolves to this public IP address.
          If the reverseFqdn is specified, then a PTR DNS record is created pointing
          from the IP address in the in-addr.arpa domain to the reverse FQDN.
      '';
    };

  };

  config._type = "azure-reserved-ip-address";

}
