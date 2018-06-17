{
    machine =
      {config, resources, pkgs, lib, ...}:
      {
        deployment.targetEnv = "ec2";
        deployment.hasFastConnection = true;
        deployment.ec2.associatePublicIpAddress = true;
        deployment.ec2.region = "us-east-1";
        deployment.ec2.instanceType = "c3.large";
        deployment.ec2.subnetId = resources.vpcSubnets.subnet-test;
        deployment.ec2.keyPair = resources.ec2KeyPairs.keypair.name;
        deployment.ec2.securityGroups = [];
        deployment.ec2.securityGroupIds = [ resources.ec2SecurityGroups.public-ssh.name ];
      };

    resources.ec2KeyPairs.keypair = { region = "us-east-1"; };
    resources.ec2SecurityGroups.public-ssh =
      { resources, ... }:
      {
        region = "us-east-1";
        vpcId = resources.vpc.vpc-test;
        rules = [{ toPort = 22; fromPort = 22; sourceIp = "0.0.0.0/0"; }];
      };
}
