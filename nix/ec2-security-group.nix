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

    accessKeyId = mkOption {
      type = types.uniq types.string;
      description = "The AWS Access Key ID.";
    };

    groupId = mkOption {
      type = types.uniq types.string;
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
          description = "The bottom of the allowed port range for this rule (TCP/UDP only)";
          type = types.uniq types.int;
        };

        toPort = mkOption {
          description = "The top of the allowed port range for this rule (TCP/UDP only)";
          type = types.uniq types.int;
        };

        typeNumber = mkOption {
          description = "ICMP type number (ICMP only, -1 for all)";
          type = types.uniq types.int;
        };

        codeNumber = mkOption {
          description = "ICMP code number (ICMP only, -1 for all)";
          type = types.uniq types.int;
        };

        sourceGroup = {
          userId = mkOption {
            description = "The AWS account ID that owns the source security group";
            type = types.uniq types.string;
          };

          groupName = mkOption {
            description = "The name of the source security group (if allowing all instances in a group access instead of an IP range)";
            type = types.uniq types.string;
          };
        };

        sourceIp = mkOption {
          description = "The source IP range (CIDR notation)";
          type = types.uniq types.string;
        };
      };
    };
  };

}
