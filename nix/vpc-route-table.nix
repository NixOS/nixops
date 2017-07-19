{ config, lib, uuid, name, ... }:

with import ./lib.nix lib;
with lib;
{
  options = {
    name = mkOption {
      default = "charon-${uuid}-${name}";
      type = types.str;
      description = "Name of the VPC network interface.";
    };
    
    accessKeyId = mkOption {
      type = types.str;
      description = "The AWS Access Key ID.";
    };

    region = mkOption {
      type = types.str;
      description = "AWS region.";
    };

    vpcId = mkOption {
      type = types.either types.str (resource "vpc");
      apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type;
      description = ''
        The ID of the VPC where the route table will be created
      '';
    };

    #TODO add propagatingVgws once virtual gtw resource is implemented.
  };

  config._type = "vpc-route-table";
}
