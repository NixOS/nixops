{
  resources.vpcSubnets.subnet-test =
    { resources, ... }:
    {
      region = "us-east-1";
      zone = "us-east-1a";
      vpcId = resources.vpc.vpc-test;
      cidrBlock = "10.0.0.0/19";
      mapPublicIpOnLaunch = true;
      tags = {
        Source = "NixOps Tests";
      };
    };
}
