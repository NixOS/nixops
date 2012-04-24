let

  configUS =
    { require = [ ./ec2-info.nix ];
      deployment.targetEnv = "ec2";
      deployment.ec2.region = "us-east-1"; 
      deployment.ec2.instanceType = "m1.small";
    };

  configEU =
    { require = [ ./ec2-info.nix ];
      deployment.targetEnv = "ec2";
      deployment.ec2.region = "eu-west-1"; 
      deployment.ec2.instanceType = "m1.small";
    };

  # Run this machine under a different account.
  configEU_eelco =
    { require = [ ./ec2-info-2.nix ];
      deployment.targetEnv = "ec2";
      deployment.ec2.region = "eu-west-1"; 
      deployment.ec2.instanceType = "m1.small";
    };

in

{
  proxy = configEU;
  backend1 = configEU_eelco;
  backend2 = configUS;
}
