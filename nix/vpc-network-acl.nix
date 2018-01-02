{ config, lib, uuid, name, ... }:

with import ./lib.nix lib;
with lib;
let
  networkAclEntry = {
    options = {
      ruleNumber = mkOption {
        type = types.int;
        description = ''
          The rule number of the entry. ACL entries are processed in asceding order by rule
          number.
        '';
      };
      protocol = mkOption {
        type = types.str;
        description = ''
          The protocol to match. If using the -1 'all' protocol, you must specify a from and
          to port of 0.
        '';
      };
      ruleAction = mkOption {
        type = types.str;
        description = ''
          The action to take. Can be either "allow" or "deny".
        ''; 
      };
      egress = mkOption {
        type = types.bool;
        description = ''
          Indicates whether this is an egress rule (rule is applied to traffic leaving the subnet).
        ''; 
      };
      cidrBlock = mkOption {
        default = null;
        type = types.nullOr types.str;
        description = ''
          The IPv4 network range to allow or deny, in CIDR notation.
        '';
      };
      ipv6CidrBlock = mkOption {
        default = null;
        type = types.nullOr types.str;
        description = ''
          The IPv6 network range to allow or deny, in CIDR notation.
        '';
      };
      icmpCode = mkOption {
        default = null;
        type = types.nullOr types.int;
        description = ''
          The ICMP type code to be used. 
        '';
      };
      icmpType = mkOption {
        default = null;
        type = types.nullOr types.int;
        description = ''
          The ICMP type to be used. 
        '';
      };
      fromPort = mkOption {
        default = null;
        type = types.nullOr types.int;
        description = ''
          The first port in the range.
        '';
      };
      toPort = mkOption {
        default = null;
        type = types.nullOr types.int;
        description = ''
          The last port in the range.
        '';
      };
    };
  };
in
{
  imports = [ ./common-ec2-auth-options.nix ];

  options = {

    name = mkOption {
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the DHCP options set.";
    };
    
    vpcId = mkOption {
      type = types.either types.str (resource "vpc");
      apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type;
      description = ''
        The Id of the associated VPC.
      '';
    };

    subnetIds = mkOption {
      default = [];
      type = types.listOf (types.either types.str (resource "vpc-subnet"));
      apply = map (x: if builtins.isString x then x else "res-" + x._name + "." + x._type + "." + "subnetId");
      description  = ''
        A list of subnet IDs to apply to the ACL to.
      '';
    };

    entries = mkOption {
      description = "The network ACL entries";
      default = [];
      type = with types; listOf (submodule networkAclEntry);
    };

    networkAclId = mkOption {
      default = "";
      type = types.str;
      description = "The network ACL id generated from AWS. This is set by NixOps";
    };
  } // import ./common-ec2-options.nix { inherit lib; };

  config._type = "vpc-network-acl";
}
