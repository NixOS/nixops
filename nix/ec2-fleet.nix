{ config, lib, uuid, name, ... }:

with import ./lib.nix lib;
with lib;

{
  imports = [ ./common-ec2-auth-options.nix ];

  options = {

    name = mkOption {
      default = "nixops-${uuid}-${name}";
      type = types.str;
      description = "Name of the ec2 fleet.";
    };

    ExcessCapacityTerminationPolicy = mkOption {
      default = "termination";
      type = types.enum [ "no-termination" "termination" ];
      description = ''
        Indicates whether running instances should be terminated
        if the total target capacity of the EC2 Fleet is decreased
        below the current size of the EC2 Fleet.'';
    };

    LaunchTemplateConfigs = mkOption {
      default = [];
      # these needs to be changed to dict i think
      type = types.listOf types.str;
      description = "The launch template configuration for the EC2 Fleet";
    };

    TerminateInstancesWithExpiration = mkOption {
      default = true;
      type = types.bool;
      description = ''
        Indicates whether running instances 
        should be terminated when the EC2 Fleet expires'';
    };

    Type = mkOption {
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
      # check if thats what we need
      default = 0;
      type = types.int;
      description = "The start date and time of the request, in UTC format";
    };

    ec2FleetValidUntil = mkOption {
      # check if thats what we need
      default = 0;
      type = types.int;
      description = "The end date and time of the request, in UTC format";
    };

    ReplaceUnhealthyInstances = mkOption {
      # this should be false
      default = false;
      type = types.bool;
      description = "Indicates whether EC2 Fleet should replace unhealthy instances.";
    };

    SpotOptions = mkOption {
      description = "ec2 fleet spotOptions.";
      default = {};
      type = with types; listOf (submodule {
        options = {
          AllocationStrategy = mkOption {
            default = "lowest-price";
            description = "Describes the configuration of Spot Instances in an EC2 Fleet.";
            type = types.enum [ "lowest-price" "diversified" ];
          };
          InstanceInterruptionBehavior = mkOption {
            default = "terminate";
            type = types.enum [ "hibernate" "stop" "hibernate" ];
            description = "The behavior when a Spot Instance is interrupted.";
          };
          InstancePoolsToUseCount = mkOption {
            default = null;
            type = types.nullOr types.int;
            description = ''
              The number of Spot pools across which to allocate your
              target Spot capacity. Valid only when Spot AllocationStrategy 
              is set to lowest-price
            '';
          };
          SingleInstanceType = mkOption {
            default = true;
            type = types.bool;
            description = "Indicates that the fleet uses a single instance type to launch all Spot Instances in the fleet.";
          };
          SingleAvailabilityZone = mkOption {
            default = true;
            type = types.bool;
            description = "Indicates that the fleet launches all Spot Instances into a single Availability Zone.";
          };
          MinTargetCapacity = mkOption {
            default = null;
            type = types.nullOr types.int;
            description = ''
              The minimum target capacity for Spot Instances in the fleet. 
              If the minimum target capacity is not reached, the fleet launches
              no instances.
            '';
          };
        };
      });
    };

    OnDemandOptions = mkOption {
      description = "The allocation strategy of On-Demand Instances in an EC2 Fleet.";
      default = {};
      type = with types; listOf (submodule {
        options = {
          AllocationStrategy = mkOption {
            default = "lowest-price";
            type = types.enum [ "lowest-price" "diversified" ];
            description = "The allocation strategy of On-Demand Instances in an EC2 Fleet.";
          };
          SingleInstanceType = mkOption {
            default = true;
            type = types.bool;
            description = "Indicates that the fleet uses a single instance type to launch all On-Demand Instances in the fleet.";
          };
          SingleAvailabilityZone = mkOption {
            default = true;
            type = types.bool;
            description = "Indicates that the fleet launches all On-Demand Instances into a single Availability Zone.";
          };
          MinTargetCapacity = mkOption {
            default = null;
            type = types.nullOr types.int;
            description = "The minimum target capacity for On-Demand Instances in the fleet. If the minimum target capacity is not reached, the fleet launches no instances.";
          };
        };
      });
    };

    TargetCapacitySpecification = mkOption {
      description = "The TotalTargetCapacity , OnDemandTargetCapacity , SpotTargetCapacity , and DefaultCapacityType structure.";
      default = {};
      type = with types; listOf (submodule {
        options = {
          TotalTargetCapacity = mkOption {
            type = types.nullOr types.int;
            description = "The number of units to request, filled using DefaultTargetCapacityType";
          };
          OnDemandTargetCapacity = mkOption {
            default = null;
            type = types.nullOr types.int;
            description = "The number of On-Demand units to request.";
          };
          SpotTargetCapacity = mkOption {
            default = null;
            type = types.nullOr types.int;
            description = "The number of Spot units to request.";
          };
          DefaultTargetCapacityType = mkOption {
            default = 1;
            type = types.nullOr types.int;
            description = "The default TotalTargetCapacity , which is either Spot or On-Demand.";
          };
        };
      });
    };

  } // import ./common-ec2-options.nix { inherit lib; } ;

  config._type = "ec2Fleet";
}