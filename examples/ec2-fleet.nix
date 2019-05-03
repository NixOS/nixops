{ region ? "us-east-1"
, accessKeyId ? "testing"
, ...
}:
{
  resources.ec2Fleet.testFleet =
    {
      inherit region accessKeyId;
      launchTemplateName = "launch-template";
      launchTemplateVersion = "1";
      launchTemplateOverrides = [];
      terminateInstancesWithExpiration = true;
      fleetRequestType = "request";
      replaceUnhealthyInstances = false;
      terminateInstancesOnDeletion = true;
      spotOptions = {
          instanceInterruptionBehavior = "terminate";
          singleAvailabilityZone = false;
          minTargetCapacity = 1;
          instancePoolsToUseCount = 3;
          singleInstanceType = false;
      };
      onDemandOptions = {
        singleAvailabilityZone = false;
        minTargetCapacity = 1;
        singleInstanceType = false;
      };
      targetCapacitySpecification = {
        totalTargetCapacity = 3;
        onDemandTargetCapacity = 1;
        spotTargetCapacity = 1;
        defaultTargetCapacityType = "spot";
      };
    };
}
