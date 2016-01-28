{ config, lib, pkgs, uuid, name, resources, ... }:

with lib;
with (import ./lib.nix lib);

{

  options = (import ./azure-mgmt-credentials.nix lib "DNS record set") // {

    name = mkOption {
      example = "test.com";
      type = types.str;
      description = ''
        Name of the Azure DNS record set.
        Use "@" for RecordSets at the apex of the zone (e.g. SOA/NS).
      '';
    };

    dnsZone = mkOption {
      example = "resources.azureDNSZones.test-com";
      type = types.either types.str (resource "azure-dns-zone");
      description = ''
        The Azure Resource Id or NixOps resource of
        the DNS zone to create the record set in.
      '';
    };

    recordType = mkOption {
      example = "CNAME";
      type = types.str;
      description = "DNS record type. Allowed values are: A, AAAA, CNAME, MX, SOA, NS, SRV, TXT.";
    };


    tags = mkOption {
      default = {};
      example = { environment = "production"; };
      type = types.attrsOf types.str;
      description = "Tag name/value pairs to associate with the DNS record set.";
    };

    properties = mkOption {
      example = {
        TTL = 300;
        CNAMERecord = {
          cname = "test.com";
        };
      };
      description = ''
        Record properties depending on record type.
        See Azure documentation for DNS record sets.
      '';
    };
  };

  config = {
    _type = "azure-dns-zone";
  };

}
