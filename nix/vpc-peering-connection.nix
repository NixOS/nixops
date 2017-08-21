{ config, lib, uuid, name, ... }:

with import ./lib.nix lib;
with lib;

{
  options = {
    
    name = mkOption {
      default = "charon-${uuid}-${name}";
      type = types.str;
      description = "Name of the VPC peering connection.";
    };

    accessKeyId = mkOption {
      type = types.str;
      description = "The AWS Access Key ID.";
    };

    region = mkOption {
      type = types.str;
      description = "AWS region.";
    };

    peerOwnerId = mkOption {
      type = types.str;
      description = ''
        The AWS account ID of the owner of the peer VPC.
      '';
    };

    peerVpcId = mkOption {
      type = types.str;
      description = ''
        The ID of the VPC with which you are creating the VPC peering connection.
      '';
    };

    vpcId = mkOption {
      type = types.either types.str (resource "vpc");
      apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type;
      description = ''
        The ID of the requester VPC.
      '';
    };
  };

  config._type = "vpc-peering-connection";
}
