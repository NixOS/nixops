{ config, lib, uuid, name, ... }:

with lib;

{

  options = {

    name = mkOption {
      type = types.str;
      description = ''
        Name of the RDS DB security group.
      '';
    };

    description = mkOption {
      type = types.str;
      description = ''
        Description of the RDS DB security group.
      ''; 
    };

    region = mkOption {
      type = types.str;
      description = "Amazon RDS DB security group region.";
    };

    accessKeyId = mkOption {
      default = "";
      type = types.str;
      description = "The AWS Access Key ID.";
    };

    rules = mkOption {
      default = [];
      type = with types; listOf (submodule {
        options = mkOption {
          cidrIp = mkOption {
            type = types.nullOr types.str;
            default = null;
          };

          securityGroupName = mkOption {
            type = types.nullOr (types.either types.str (resource "ec2-security-group"));
            apply = x: if (!x isString) then x.name else x;
            default = null;
          };

          securityGroupId = mkOption {
            type = types.nullOr (types.either types.str (resource "ec2-security-group"));
            apply = x: if (!x isString) then x.groupId else x;
            default = null;
          };

          securityGroupOwnerId = mkOption {
            type = types.nullOr types.str;
            default = null;
          };
        };
      });
    };

  };

  config._type = "ec2-rds-security-group";
}
