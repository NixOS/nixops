let

  configUS =
    { require = [ ./ec2-info.nix ];
      deployment.targetEnv = "ec2";
      deployment.ec2.region = "us-east-1"; 
      deployment.ec2.instanceType = "m1.large";
    };

  configEU =
    { require = [ ./ec2-info.nix ];
      deployment.targetEnv = "ec2";
      deployment.ec2.region = "eu-west-1"; 
      deployment.ec2.instanceType = "m1.large";
    };

in

{
  proxy = configUS;
  backend1 = configUS;
  backend2 = configEU;
}
