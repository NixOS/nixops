{ config, lib, uuid, name, ... }:

with lib;

{

  options = {

    name = mkOption {
      default = "charon-${uuid}-${name}";
      type = types.str;
      description = "Name of the security group.";
    };

    description = mkOption {
      default = "NixOps-provisioned group ${name}";
      type = types.str;
      description = "Informational description of the security group.";
    };

    region = mkOption {
      type = types.str;
      description = "Amazon EC2 region.";
    };

    accessKeyId = mkOption {
      default = "";
      type = types.str;
      description = "The AWS Access Key ID.";
    };

    groupId = mkOption {
      default = null;
      type = types.uniq (types.nullOr types.str);
      description = "The security group ID. This is set by NixOps.";
    };

    vpcId = mkOption {
      default = null;
      type = types.uniq (types.nullOr types.str);
      description = "The VPC ID to create security group in.";
    };

    rules = mkOption {
      type = types.listOf types.optionSet;
      description = "The security group's rules.";
      default = {};
      options = {
        protocol = mkOption {
          default = "tcp";
          description = "The protocol (tcp, udp, or icmp) that this rule describes.";
          type = types.str;
        };

        fromPort = mkOption {
          default = null;
          description = "The bottom of the allowed port range for this rule (TCP/UDP only).";
          type = types.uniq (types.nullOr types.int);
        };

        toPort = mkOption {
          default = null;
          description = "The top of the allowed port range for this rule (TCP/UDP only).";
          type = types.uniq (types.nullOr types.int);
        };

        typeNumber = mkOption {
          default = null;
          description = "ICMP type number (ICMP only, -1 for all).";
          type = types.uniq (types.nullOr types.int);
        };

        codeNumber = mkOption {
          default = null;
          description = "ICMP code number (ICMP only, -1 for all).";
          type = types.uniq (types.nullOr types.int);
        };

        sourceGroup = {
          ownerId = mkOption {
            default = null;
            description = "The AWS account ID that owns the source security group.";
            type = types.uniq (types.nullOr types.str);
          };

          groupName = mkOption {
            default = null;
            description = "The name of the source security group (if allowing all instances in a group access instead of an IP range).";
            type = types.uniq (types.nullOr types.str);
          };
        };

        sourceIp = mkOption {
          default = null;
          description = "The source IP range (CIDR notation).";
          type = types.uniq (types.nullOr types.str);
        };
      };
    };
  };

  config._type = "ec2-security-group";

}
