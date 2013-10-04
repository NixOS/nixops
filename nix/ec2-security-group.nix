{ config, pkgs, uuid, name, ... }:

with pkgs.lib;

{

  options = {

    name = mkOption {
      default = "charon-${uuid}-${name}";
      type = types.uniq types.string;
      description = "Name of the security group.";
    };

    description = mkOption {
      default = "nixops-provisioned group ${name}";
      type = types.string;
      description = "Informational description of the security group";
    };

    region = mkOption {
      type = types.uniq types.string;
      description = "Amazon EC2 region.";
    };

    accessKeyId = mkOption {
      default = "";
      type = types.uniq types.string;
      description = "The AWS Access Key ID.";
    };

    groupId = mkOption {
      default = null;
      type = types.uniq (types.nullOr types.string);
      description = "The security group ID. This is set by NixOps.";
    };

    rules = mkOption {
      type = types.listOf types.optionSet;
      description = "The security group's rules";
      default = {};
      options = {
        protocol = mkOption {
          default = "tcp";
          description = "The protocol (tcp, udp, or icmp) that this rule describes";
          type = types.uniq types.string;
        };

        fromPort = mkOption {
          default = null;
          description = "The bottom of the allowed port range for this rule (TCP/UDP only)";
          type = types.uniq (types.nullOr types.int);
        };

        toPort = mkOption {
          default = null;
          description = "The top of the allowed port range for this rule (TCP/UDP only)";
          type = types.uniq (types.nullOr types.int);
        };

        typeNumber = mkOption {
          default = null;
          description = "ICMP type number (ICMP only, -1 for all)";
          type = types.uniq (types.nullOr types.int);
        };

        codeNumber = mkOption {
          default = null;
          description = "ICMP code number (ICMP only, -1 for all)";
          type = types.uniq (types.nullOr types.int);
        };

        sourceGroup = {
          ownerId = mkOption {
            default = null;
            description = "The AWS account ID that owns the source security group";
            type = types.uniq (types.nullOr types.string);
          };

          groupName = mkOption {
            default = null;
            description = "The name of the source security group (if allowing all instances in a group access instead of an IP range)";
            type = types.uniq (types.nullOr types.string);
          };
        };

        sourceIp = mkOption {
          default = null;
          description = "The source IP range (CIDR notation)";
          type = types.uniq (types.nullOr types.string);
        };
      };
    };
  };

}
