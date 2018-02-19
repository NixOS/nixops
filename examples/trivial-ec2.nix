{
  machine =
    { imports = [ ./ec2-info.nix ];
      deployment.targetEnv = "ec2";
      deployment.ec2.region = "us-east-1";
      deployment.ec2.instanceType = "t2.medium";
    };
}
