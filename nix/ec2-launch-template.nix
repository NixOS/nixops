{ config, lib, uuid, name, ... }:

with import ./lib.nix lib;
with lib;

{
  imports = [ ./common-ec2-auth-options.nix ];

  options = {

    templateName = mkOption {
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the launch template.";
    };

    templateId = mkOption {
      default = "";
      type = types.str;
      description = "ec2 launch template ID (set by NixOps)";
    };

    versionDescription = mkOption {
      default = "";
      type = types.str;
      description = "A description for the version of the launch template";
    };


    # we might want to make this in a way similar to ec2.nix
    ebsOptimized = mkOption {
      default = true;
      description = ''
        Whether the EC2 instance should be created as an EBS Optimized instance.
      '';
      type = types.bool;
    };

    userData = mkOption {
      default = null;
      type = types.nullOr types.str;
      description = ''
        The user data to make available to the instance.
        It should be valid nix expressions.
        '';
    };

    # add support for ec2 then move to common
    disableApiTermination = mkOption {
      default = false;
      type = types.bool;
      description = ''
        If set to true , you can't terminate the instance
        using the Amazon EC2 console, CLI, or API.
      '';
    };

    # add support for ec2 then move to common
    instanceInitiatedShutdownBehavior = mkOption {
      default = "terminate";
      type = types.enum ["stop" "terminate"];
      description = ''
        Indicates whether an instance stops or terminates
        when you initiate shutdown from the instance (using
        the operating system command for system shutdown).
      '';
    };
    # add support for ec2 then move to common
    networkInterfaceId = mkOption {
      default = "";
      # must get the id fro mthe name
      type = with types; either str (resource "vpc-network-interface");
      apply = x: if builtins.isString x then x else "res-" + x._name "." + x._type;
      description = ''
        The ID of the network interface.
      '';
    };
    # add support for ec2 then move to common
    monitoring = mkOption {
      default = false;
      type = types.bool;
      description = ''
        if set to true, detailed monitoring is enabled.
        Otherwise, basic monitoring is enabled.
      '';
    };

    privateIpAddresses = mkOption {
      default = null;
      type = with types; (nullOr (listOf str));
      description = ''
        One or more secondary private IPv4 addresses.
      '';
    };
    secondaryPrivateIpAddressCount = mkOption {
      default = null;
      type = types.nullOr types.int;
      description = ''
        The number of secondary private IPv4 addresses to assign to a network interface.
        When you specify a number of secondary IPv4 addresses, Amazon EC2 selects these
        IP addresses within the subnet's IPv4 CIDR range.
        You can't specify this option and specify privateIpAddresses in the same time.
      '';
    };

  }// (import ./common-ec2-options.nix { inherit lib; }) // (import ./common-ec2-instance-options.nix { inherit lib; });

  config._type = "ec2-launch-template";
}