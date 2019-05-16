{ region ? "us-east-1"
, accessKeyId ? "testing"
, ...
}:
{
  resources.ec2Fleet.testFleet =
    {resources, ...}:
    {
      inherit region accessKeyId;
      launchTemplateName = resources.ec2LaunchTemplate.testlaunchtemplate;
      launchTemplateVersion = resources.ec2LaunchTemplate.testlaunchtemplate;
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

  resources.ec2LaunchTemplate.testlaunchtemplate =
    {resources, ...}:
    {
      inherit region accessKeyId;
      name = "lt-with-nixops";
      description = "lt with nix";
      versionDescription = "version 1 ";
      LTData = {
        instanceType = "m5.large";
        imageId = "ami-009c9c3f1af480ff3";
        instanceProfile = resources.iamRoles.role.name;
        subnetId = "subnet-xxxxxx";
        keyName = resources.ec2KeyPairs.kp;
        userData =''
          { valid nix expressions }
        '';
        #securityGroupIds = [resources.ec2SecurityGroups.sg];
      };
    };

resources.iamRoles.role =
    {
      inherit accessKeyId;
      policy = builtins.toJSON {
        Statement = [
          {
            Action =
              [ "s3:Get*"
                "s3:Put*"
                "s3:List*"
                "s3:DeleteObject"
              ];
            Effect = "Allow";
            Resource = "*";
          }
        ];
      };
    };
resources.ec2SecurityGroups.sg =
  { config, resources, ... }:
    let
      entry = ip:
        {
          fromPort = 22;
          toPort = 22;
          sourceIp = if builtins.isString ip then "${ip}/32" else ip;
        } ;
      ips = [ "22.22.22.22" ];
    in
      {
        inherit region accessKeyId;
        description = "Security group for nixos testing";
        rules = map entry ips;
        name = "nixos-test-ec2";
      };
  resources.ec2KeyPairs.kp =
    { inherit region accessKeyId; };
}
