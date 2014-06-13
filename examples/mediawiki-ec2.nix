let

  config =
    { imports = [ ./ec2-info.nix ];
      deployment.targetEnv = "ec2";
      deployment.ec2.region = "us-east-1";
      deployment.ec2.instanceType = "m1.large";
    };

in

{
  webserver = config;
  database = config;
}
