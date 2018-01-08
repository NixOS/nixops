{ config, lib, uuid, name, ... }:

with lib;

{

  options = {

    name = mkOption {
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the recordset.";
    };

    region = mkOption {
      type = types.str;
      description = "AWS region.";
    };

    accessKeyId = mkOption {
      type = types.str;
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

    zoneId = mkOption {
      type = types.nullOr types.str;
      default = null;
      description = "The DNS hosted zone id. If null, the zoneName will be used to look up the zoneID";
    };

    zoneName = mkOption {
      type = types.nullOr types.str;
      default = null;
      description = "The DNS name of the hosted zone";
    };

    domainName = mkOption {
      type = types.str;
      description = "The DNS name to bind.";
    };

    ttl = mkOption {
      type = types.int;
      default = 300;
      example = 300;

      description = ''
        The time to live (TTL) for the A record created for the
        specified DNS hostname.
      '';
    };

    recordType = mkOption {
      type = types.enum [ "SOA" "A" "AAAA" "TXT" "NS" "CNAME" "MX" "NAPT" "PTR" "SRV" "SPF" ];
      default = "A";

      description = ''
        DNS record type
      '';
    };

    recordValue = mkOption {
      type = types.str;

      description = ''
        The value of the DNS record 
        (e.g. IP adress in case of an A or AAA record type, 
         or a DNS name in case of a CNAME record type)
      '';
    };
  };
}
