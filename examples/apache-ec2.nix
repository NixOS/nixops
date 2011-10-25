let

  config =
    { deployment.targetEnv = "ec2";
      deployment.ec2.zone = "us-east-1";
      deployment.ec2.instanceType = "m1.large";
      deployment.ec2.keyPair = "eelco";
      deployment.ec2.securityGroup = "eelco-test";
    };

in

{
  proxy = config;
  backend1 = config;
  backend2 = config;
}
