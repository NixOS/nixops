{ config, lib, uuid, name, ... }:

with import ./lib.nix lib;
with lib;

{
  imports = [ ./common-ec2-auth-options.nix ];

  options = {

    fleetId = mkOption {
      default = "";
      type = types.str;
      description = "EC2 fleet ID (set by NixOps)";
    };

    fleetInstances = mkOption {
      default = {};
      type = with types; either attrs lines;
      description = "a set containing all the instnaces and their configuration set by nixops";
    };

    excessCapacityTerminationPolicy = mkOption {
      default = "termination";
      type = types.enum [ "no-termination" "termination" ];
      description = ''
        Indicates whether running instances should be terminated
        if the total target capacity of the EC2 Fleet is decreased
        below the current size of the EC2 Fleet.'';
    };

    launchTemplateName = mkOption {
      type = with types; either str (resource "ec2-launch-template");
      apply = x: if builtins.isString x then x else x.name;
      description = "The launch template configuration for the EC2 Fleet";
    };
    launchTemplateVersion = mkOption {
      default = "1";
      type = with types; either str (resource "ec2-launch-template");
      apply = x: if builtins.isString x then x else x.version;
      description = "The launch template version to use";
    };
    launchTemplateOverrides = mkOption {
      default = [];
      # these needs to be changed to dict i think
      type = types.listOf types.attrs;
      description = "Specific parameters to override the parameters in the launch template.";
    };

    terminateInstancesWithExpiration = mkOption {
      default = true;
      type = types.bool;
      description = ''
        Indicates whether running instances 
        should be terminated when the EC2 Fleet expires'';
    };

    fleetRequestType = mkOption {
      # check if thats what we need
      default = "maintain";
      type = types.enum [ "request" "maintain" "instant" ];
      description = ''
        The type of the request. By default, the EC2 Fleet places
        an asynchronous request for your desired capacity, and 
        maintains it by replenishing interrupted Spot Instances
        (maintain ). A value of instant places a synchronous one-time
        request, and returns errors for any instances that could not
        be launched. A value of request places an asynchronous one-time
        request without maintaining capacity or submitting requests
        in alternative capacity pools if capacity is unavailable. 
      '';
    };

    ec2FleetValidFrom = mkOption {
      default = null;
      type = types.nullOr types.int;
      description = "The start date and time of the request, in UTC format";
    };

    ec2FleetValidUntil = mkOption {
      default = null;
      type = types.nullOr types.int;
      description = "The end date and time of the request, in UTC format";
    };

    replaceUnhealthyInstances = mkOption {
      # this should be false
      default = false;
      type = types.bool;
      description = "Indicates whether EC2 Fleet should replace unhealthy instances.";
    };

    terminateInstancesOnDeletion = mkOption {
      default = false;
      type = types.bool;
      description = "Indicates whether to terminate instances for an EC2 Fleet if it is deleted successfully.";
    };

    spotOptions = {
      allocationStrategy = mkOption {
        default = "lowestPrice";
        type = types.enum [ "lowestPrice" "diversified" ];
        description = "Describes the configuration of Spot Instances in an EC2 Fleet.";
      };
      instanceInterruptionBehavior = mkOption {
        default = "terminate";
        type = types.enum [ "hibernate" "stop" "terminate" ];
        description = "The behavior when a Spot Instance is interrupted.";
      };
      instancePoolsToUseCount = mkOption {
        default = 1;
        type = types.int;
        description = ''
          The number of Spot pools across which to allocate your
          target Spot capacity. Valid only when Spot AllocationStrategy
          is set to lowest-price
        '';
      };
      singleInstanceType = mkOption {
        default = true;
        type = types.bool;
        description = "Indicates that the fleet uses a single instance type to launch all Spot Instances in the fleet.";
      };
      singleAvailabilityZone = mkOption {
        default = true;
        type = types.bool;
        description = "Indicates that the fleet launches all Spot Instances into a single Availability Zone.";
      };
      minTargetCapacity = mkOption {
        default = null;
        type = types.nullOr types.int;
        description = ''
          The minimum target capacity for Spot Instances in the fleet.
          If the minimum target capacity is not reached, the fleet launches
          no instances.
        '';
      };
    };

    onDemandOptions = {
      allocationStrategy = mkOption {
        default = "lowestPrice";
        type = types.enum [ "lowestPrice" "diversified" ];
        description = "The allocation strategy of On-Demand Instances in an EC2 Fleet.";
      };
      singleInstanceType = mkOption {
        default = true;
        type = types.bool;
        description = "Indicates that the fleet uses a single instance type to launch all On-Demand Instances in the fleet.";
      };
      singleAvailabilityZone = mkOption {
        default = true;
        type = types.bool;
        description = "Indicates that the fleet launches all On-Demand Instances into a single Availability Zone.";
      };
      minTargetCapacity = mkOption {
        default = null;
        type = types.nullOr types.int;
        description = "The minimum target capacity for On-Demand Instances in the fleet. If the minimum target capacity is not reached, the fleet launches no instances.";
      };
    };

    targetCapacitySpecification = {
      totalTargetCapacity = mkOption {
        type = types.int;
        description = "The number of units to request, filled using DefaultTargetCapacityType";
      };
      onDemandTargetCapacity = mkOption {
        default = 0;
        type = types.nullOr types.int;
        description = "The number of On-Demand units to request.";
      };
      spotTargetCapacity = mkOption {
        default = 0;
        type = types.int;
        description = "The number of Spot units to request.";
      };
      defaultTargetCapacityType = mkOption {
        default = "on-demand";
        type = types.enum [ "spot" "on-demand" ];
        description = "The default TotalTargetCapacity , which is either Spot or On-Demand.";
      };
    };
  } // import ./common-ec2-options.nix { inherit lib; } ;

  config._type = "ecc-fleet";
}