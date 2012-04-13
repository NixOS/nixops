{
  defaults =
    { config, pkgs, ... }:
    { require = [ ./ec2-info.nix ];
      deployment.targetEnv = "ec2";
      deployment.ec2.region = pkgs.lib.mkDefault "eu-west-1";
      deployment.ec2.instanceType = "m1.small";
    };
    
  backend2.deployment.ec2.region = "us-east-1";
  backend2.deployment.ec2.tags.DummyTag = "some random blabla";
  backend2.deployment.ec2.tags.AnotherTag = "more blabla";
}
