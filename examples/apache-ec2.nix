{
  defaults =
    { config, pkgs, ... }:
    { imports = [ ./ec2-info-example.nix ];
      deployment.targetEnv = "ec2";
      deployment.ec2.region = pkgs.lib.mkDefault "eu-west-1";
      deployment.ec2.instanceType = "t2.large";
    };
    
  backend2 = { ... }: {
    deployment.ec2.region = "us-east-1";
    deployment.ec2.tags.DummyTag = "some random blabla";
    deployment.ec2.tags.AnotherTag = "more blabla";
  };
}
