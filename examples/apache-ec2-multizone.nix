let

  configUS =
    { imports = [ ./ec2-info.nix ];
      deployment.targetEnv = "ec2";
      deployment.ec2.region = "us-east-1"; 
      deployment.ec2.instanceType = "m1.small";
      deployment.ec2.privateKey = "/home/eelco/.ec2/logicblox/id_rsa-eelco-logicblox-us-east-1";
    };

  configEU =
    { imports = [ ./ec2-info.nix ];
      deployment.targetEnv = "ec2";
      deployment.ec2.region = "eu-west-1"; 
      deployment.ec2.instanceType = "m1.small";
    };

  # Run this machine under a different account.
  configEU_eelco =
    { imports = [ ./ec2-info-2.nix ];
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
