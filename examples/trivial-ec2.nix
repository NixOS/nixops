{
  #network = {
    #  datadogNotify = true;
    #datadogDowntime = true;
    #datadogDowntimeSeconds = 7200;
    #};
  resources.iamRoles.role = { lib, ... }:
  {
    accessKeyId = "nixos-tests";
    policy = builtins.toJSON
      {
        Statement = [
          {
            Effect = "Allow";
            Action = [ "ses:SendEmail" "ses:SendRawEmail"];
            Resource = "*";
          }
        ];
      };
  };

  resources.iamRoles.role2 = { lib, ... }:
  {
    accessKeyId = "nixos-tests";
    policy = builtins.toJSON
      {
        Statement = [
          {
            Effect = "Allow";
            Action = [ "ses:SendEmail" "ses:SendRawEmail"];
            Resource = "*";
          }
        ];
      };
  };


  machine = { resources, ... }:
    { imports = [ ./ec2-info.nix ];
      deployment.targetEnv = "ec2";
      deployment.ec2.region = "us-east-1";
      deployment.ec2.instanceType = "t2.medium";
      #deployment.ec2.instanceProfile = resources.iamRoles.role.name;
    };

  machine2 = { resources, ... }:
    { imports = [ ./ec2-info.nix ];
      deployment.targetEnv = "ec2";
      deployment.ec2.region = "us-east-1";
      deployment.ec2.instanceType = "t2.medium";
      deployment.ec2.instanceProfile = resources.iamRoles.role2.name;
    };


}
