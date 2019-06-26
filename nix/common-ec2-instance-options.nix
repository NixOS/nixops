# Options shared between an ec2 resource type and the
# launch template resource in EC2
# instances.

{ lib }:

with lib;
with import ./lib.nix lib;
{

  zone = mkOption {
    default = "";
    example = "us-east-1c";
    type = types.str;
    description = ''
      The EC2 availability zone in which the instance should be
      created.  If not specified, a zone is selected automatically.
    '';
  };

  tenancy = mkOption {
    default = "default";
    type = types.enum [ "default" "dedicated" "host" ];
    description = ''
      The tenancy of the instance (if the instance is running in a VPC).
      An instance with a tenancy of dedicated runs on single-tenant hardware.
      An instance with host tenancy runs on a Dedicated Host, which is an
      isolated server with configurations that you can control.
    '';
  };

  ebsInitialRootDiskSize = mkOption {
    default = 0;
    type = types.int;
    description = ''
      Preferred size (G) of the root disk of the EBS-backed instance. By
      default, EBS-backed images have a size determined by the
      AMI. Only supported on creation of the instance.
    '';
  };

  ami = mkOption {
    example = "ami-00000000";
    type = types.str;
    description = ''
      EC2 identifier of the AMI disk image used in the virtual
      machine.  This must be a NixOS image providing SSH access.
    '';
  };

  instanceType = mkOption {
    default = "m1.small";
    example = "m1.large";
    type = types.str;
    description = ''
      EC2 instance type.  See <link
      xlink:href='http://aws.amazon.com/ec2/instance-types/'/> for a
      list of valid Amazon EC2 instance types.
    '';
  };

  instanceProfile = mkOption {
    default = "";
    example = "rolename";
    type = types.str;
    description = ''
      The name of the IAM Instance Profile (IIP) to associate with
      the instances.
    '';
  };

  keyPair = mkOption {
    example = "my-keypair";
    type = types.either types.str (resource "ec2-keypair");
    apply = x: if builtins.isString x then x else x.name;
    description = ''
      Name of the SSH key pair to be used to communicate securely
      with the instance.  Key pairs can be created using the
      <command>ec2-add-keypair</command> command.
    '';
  };

  securityGroupIds = mkOption {
    default = [ "default" ];
    type = types.listOf types.str;
    description = ''
      Security Group IDs for the instance. Necessary if starting
      an instance inside a VPC/subnet. In the non-default VPC, security
      groups needs to be specified by ID and not name.
    '';
  };

  subnetId = mkOption {
    default = "";
    example = "subnet-00000000";
    type = types.either types.str (resource "vpc-subnet");
    apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type;
    description = ''
      The subnet inside a VPC to launch the instance in.
    '';
  };

  associatePublicIpAddress = mkOption {
    default = false;
    type = types.bool;
    description = ''
      If instance in a subnet/VPC, whether to associate a public
      IP address with the instance.
    '';
  };

  placementGroup = mkOption {
    default = "";
    example = "my-cluster";
    type = types.either types.str (resource "ec2-placement-group");
    apply = x: if builtins.isString x then x else x.name;
    description = ''
      Placement group for the instance.
    '';
  };

  spotInstancePrice = mkOption {
    default = 0;
    type = types.int;
    description = ''
      Price (in dollar cents per hour) to use for spot instances request for the machine.
      If the value is equal to 0 (default), then spot instances are not used.
    '';
  };

  spotInstanceRequestType = mkOption {
    default = "one-time";
    type = types.enum [ "one-time" "persistent" ];
    description = ''
      The type of the spot instance request. It can be either "one-time" or "persistent".
    '';
  };

  spotInstanceInterruptionBehavior = mkOption {
    default = "terminate";
    type = types.enum [ "terminate" "stop" "hibernate" ];
    description = ''
      Whether to terminate, stop or hibernate the instance when it gets interrupted.
      For stop, spotInstanceRequestType must be set to "persistent".
    '';
  };

  spotInstanceTimeout = mkOption {
    default = 0;
    type = types.int;
    description = ''
      The duration (in seconds) that the spot instance request is
      valid. If the request cannot be satisfied in this amount of
      time, the request will be cancelled automatically, and NixOps
      will fail with an error message. The default (0) is no timeout.
    '';
  };
}
