{ region ? "us-east-1"
, accessKeyId ? "test"
, vpcId ? "vpc-xxxxxx"
, subnetId ? "subnet-xxxxxx"
, securityGroup ? "Admin"
, rootVolumeSize ? 60
, ebsVolumeSize ? 40
, ...
}:
{

  resources.ec2Fleet.testFleet =
    {resources, ...}:
    {
      inherit region accessKeyId;
      launchTemplateName = resources.ec2LaunchTemplate.testlaunchtemplate;
      launchTemplateVersion = resources.ec2LaunchTemplate.testlaunchtemplate;
      launchTemplateOverrides = [{InstanceType = "r3.4xlarge"; SubnetId = "subnet-xxxxxx";}
        {InstanceType = "r3.4xlarge"; SubnetId = "subnet-xxxxxx";}
        {InstanceType = "r3.4xlarge"; SubnetId = "subnet-xxxxxx";}
        {InstanceType = "r3.4xlarge"; SubnetId = "subnet-xxxxxx";}
        {InstanceType = "r3.4xlarge"; SubnetId = "subnet-xxxxxx";}
        {InstanceType = "r3.4xlarge"; SubnetId = "subnet-xxxxxx";}
        {InstanceType = "r4.8xlarge"; SubnetId = "subnet-xxxxxx";}
        {InstanceType = "r4.8xlarge"; SubnetId = "subnet-xxxxxx";}
        {InstanceType = "r4.8xlarge"; SubnetId = "subnet-xxxxxx";}
        {InstanceType = "r4.8xlarge"; SubnetId = "subnet-xxxxxx";}
        {InstanceType = "r4.8xlarge"; SubnetId = "subnet-xxxxxx";}
        {InstanceType = "r4.8xlarge"; SubnetId = "subnet-xxxxxx";}];
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
          allocationStrategy = "capacityOptimized";
      };
      onDemandOptions = {
        singleAvailabilityZone = false;
        minTargetCapacity = 1;
        singleInstanceType = false;
        allocationStrategy = "lowestPrice";
      };
      targetCapacitySpecification = {
        totalTargetCapacity = 20;
        onDemandTargetCapacity = 2;
        spotTargetCapacity = 6;
        defaultTargetCapacityType = "spot";
      };
    };

  resources.ec2LaunchTemplate.testlaunchtemplate =
    {resources, ...}:
    {
      inherit region accessKeyId;
      templateName = "lt-with-nixops";
      description = "lt with nix";
      versionDescription = "version 1 ";
      instanceType = "m5.large";
      ami = "ami-009c9c3f1af480ff3";
      instanceProfile = resources.iamRoles.role.name;
      subnetId = "subnet-xxxxxx";
      keyPair = resources.ec2KeyPairs.kp;
      ebsInitialRootDiskSize = 30;
      associatePublicIpAddress = true;
      userData =''
          valid nix expressions
       '';
      securityGroupIds = [ securityGroup ];
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

  resources.ec2KeyPairs.kp =
    { inherit region accessKeyId; };
}