{
  defaults =
    { config, pkgs, ... }:
    { deployment.targetEnv = "ec2";
      deployment.ec2.region = pkgs.lib.mkDefault "eu-west-1";
      deployment.ec2.instanceType = "m1.small";
      deployment.ec2.keyPair = "eelco";
      deployment.ec2.securityGroups = [ "eelco-test" ];
    };
    
  backend2.deployment.ec2.region = "us-east-1";
  backend2.deployment.ec2.tags.DummyTag = "some random blabla";
  backend2.deployment.ec2.tags.AnotherTag = "more blabla";
}
