{ config, lib, ... }:

with lib;
with import ./lib.nix lib;

{

  options = {

    region = mkOption {
      type = types.str;
      description = "AWS region.";
    };

    accessKeyId = mkOption {
      type = types.str;
      description = "The AWS Access Key ID.";
    };

    fileSystem = mkOption {
      type = types.either types.str (resource "elastic-file-system");
      apply = x: if builtins.isString x then x else "res-" + x._name;
      description = "The Elastic File System to which this mount target refers.";
    };

    subnet = mkOption {
      type = types.str;
      description = "The EC2 subnet in which to create this mount target.";
    };

    ipAddress = mkOption {
      type = types.nullOr types.str;
      default = null;
      description = "The IP address of the mount target in the subnet. If unspecified, EC2 will automatically assign an address.";
    };

    securityGroups = mkOption {
      type = types.listOf types.str;
      default = [];
      description = "The EC2 security groups associated with the mount target's network interface.";
    };

  } // import ./common-ec2-options.nix { inherit lib; };

  config = {
    _type = "elastic-file-system-mount-target";
  };

}
