{ config, pkgs, uuid, name, ... }:

with pkgs.lib;

{

  options = {

    # Pass-through of the resource name.
    _name = mkOption {
      default = name;
      visible = false;
      description = "Name of the resource.";
    };

    name = mkOption {
      example = "My Big Fat Disk";
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Description of the EBS volume.  This is the <literal>Name</literal> tag of the disk.";
    };

    region = mkOption {
      example = "us-east-1";
      type = types.str;
      description = "Amazon EC2 region.";
    };

    zone = mkOption {
      example = "us-east-1c";
      type = types.str;
      description = ''
        The EC2 availability zone in which the volume should be
        created.
      '';
    };

    accessKeyId = mkOption {
      type = types.str;
      description = "The AWS Access Key ID.";
    };

    size = mkOption {
      example = 100;
      type = types.int;
      description = "Volume size (in gigabytes).";
    };

    # Hack to allow checking whether a resource is an EBS volume.
    type = mkOption {
      default = "ebs-volume";
      visible = false;
    };

  };

}
