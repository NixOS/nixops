{ config, lib, uuid, name, ... }:

with lib;
with import ./lib.nix lib;

{

  imports = [ ./common-ec2-auth-options.nix ];

  options = {

    groupName = mkOption {
      type = types.str;
      description = ''
        Name of the RDS DB subnet group.
      '';
    };

    description = mkOption {
      type = types.str;
      description = ''
        Description of the RDS DB subnet group.
      ''; 
    };

    subnetIds = mkOption {
      default = [ ];
      type = types.listOf (types.either types.str (resource "vpc-subnet"));
      apply = map (x: if builtins.isString x then x else "res-" + x._name + "." + x._type + "." + "subnetId");
      description = ''
        The EC2 Subnet IDs for the DB subnet group.
      '';
    };

  };

  config._type = "ec2-rds-subnet-group";
}
