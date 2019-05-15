{ config, lib, uuid, name, ... }:

with lib;

{
  imports = [ ./common-ec2-auth-options.nix ];

  options = {

    name = mkOption {
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the launch template.";
    };

    templateId = mkOption {
      default = "";
      type = types.str;
      description = "ec2 launch template ID (set by NixOps)";
    };

    version = mkOption {
      default = "1";
      type = types.str;
      description = "The launch template version";
    };

    versionDescription = mkOption {
      default = "";
      type = types.str;
      description = "A description for the version of the launch template";
    };

    LTData = mkOption {
      description = "The launch template definition.";
      default = {};
      type = with types; submodule {
        options = {
          # we might want to make this in a way similar to ec2.nix
          ebsOptimized = mkOption {
            default = true;
            description = ''
              Whether the EC2 instance should be created as an EBS Optimized instance.
            '';
            type = types.bool;
          };

          instanceProfile = mkOption {
            default = "";
            example = "rolename";
            type = with types; (nullOr (either str (resource "ec2-iam-role")));
            apply = x: if builtins.isString x then x else x.name;
            description = ''
              The name of the IAM Instance Profile (IIP) to associate with
              the instances.
            '';
          };

          imageId = mkOption {
            #put nixos 18.03 and check if we can get the latest like how we do in ec2
            default = "";
            description = "The ID pf the AMI to use to launch instances";
            type = types.str;
          };

          instanceType = mkOption {
            default = null;
            example = "m1.large";
            type = with types; (nullOr str);
            description = ''
              EC2 instance type.  See <link
              xlink:href='http://aws.amazon.com/ec2/instance-types/'/> for a
              list of valid Amazon EC2 instance types.
            '';
          };

          keyName = mkOption {
            default = "";
            example = "ssh-keypair";
            type = with types; (nullOr (either str (resource "ec2-keypair")));
            apply = x: if builtins.isString x then x else x.name;
            description = ''
              Name of the SSH key pair to be used to communicate securely
              with the instance.  Key pairs can be created using the
              <command>ec2-add-keypair</command> command.
          '';
          };

          userData = mkOption {
            default = "";
            type = types.str;
            description = ''
              The Base64-encoded user data to make available to the instance.
              It should be valid nix expressions.
              '';
          };

          securityGroupIds = mkOption {
            default = [];
            example = [ "sg-123abc" ];
            type = with types; listOf (either str (resource "ec2-security-group"));
            apply = map (x: if builtins.isString x then x else x. groupId);
            description = ''
              Security groups Ids for the instance. These determine the
              firewall rules applied to the instance.
            '';
          };

          disableApiTermination = mkOption {
            default = false;
            type = types.bool;
            description = ''
              If set to true , you can't terminate the instance
              using the Amazon EC2 console, CLI, or API.
            '';
          };

          instanceInitiatedShutdownBehavior = mkOption {
            default = "terminate";
            type = types.enum ["stop" "terminate"];
            description = ''
              Indicates whether an instance stops or terminates
              when you initiate shutdown from the instance (using
              the operating system command for system shutdown).
            '';
          };

          # placement options
          placementGroup = mkOption {
            default = "";
            example = "my-cluster";
            type = with types; (nullOr (either str (resource "ec2-placement-group")));
            apply = x: if builtins.isString x then x else x.name;
            description = ''
              Placement group for the instance.
            '';
          };
          availabilityZone = mkOption {
            default = null;
            example = "us-east-1c";
            type = with types; (nullOr str);
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

          # Network interfaces options
          associatePublicIpAddress = mkOption {
            default = true;
            type = types.bool;
            description = ''
              Associates a public IPv4 address with eth0 for a new network interface.
            '';
          };
          networkInterfaceId = mkOption {
            default = "";
            # must get the id fro mthe name
            type = with types; (nullOr (either str (resource "vpc-network-interface")));
            apply = x: if builtins.isString x then x else x.name;
            description = ''
              The ID of the network interface.
            '';
          };
          subnetId = mkOption {
            default = "";
            example = "subnet-12345678";
            type = with types; (either str (resource "vpc-subnet"));
            apply = x: if builtins.isString x then x else "res-" + x._name + "." + x._type;
            description = ''
              The subnet inside a VPC to launch the instance in.
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

          monitoring = mkOption {
            default = false;
            type = types.bool;
            description = ''
              if set to true, detailed monitoring is enabled.
              Otherwise, basic monitoring is enabled.
            '';
          };

          instanceMarketOptions = mkOption {
            # we can create different options but i think users can take care of this themselves
            # make sure that this is json and transform it to a dict if thats possible
            default = null;
            type = with types; (nullOr str);
            description = ''
              {
                'MarketType': 'spot',
                'SpotOptions': {
                  'MaxPrice': 'string',
                  'SpotInstanceType': 'one-time'|'persistent',
                  'BlockDurationMinutes': 123,
                  'ValidUntil': datetime(2015, 1, 1),
                  'InstanceInterruptionBehavior': 'hibernate'|'stop'|'terminate'
                }
              }
            '';
          };
        };
      };
    };
  }// import ./common-ec2-options.nix { inherit lib; };

  config._type = "ec2-launch-template";
}