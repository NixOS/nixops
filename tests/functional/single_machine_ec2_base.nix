let
  region = "us-east-1";
in
{
  resources.ec2KeyPairs.my-key-pair =
    { inherit region; };

  resources.ec2SecurityGroups.ssh-security-group = {
    inherit region;
    description = "Security group for nixops tests";
    rules = [ {
      fromPort = 22;
      toPort = 22;
      sourceIp = "0.0.0.0/0";
    } ];
  };

  machine =
    { resources, ... }:
    {
      deployment.targetEnv = "ec2";
      deployment.ec2 = {
        inherit region;
        instanceType = "m1.small";
        securityGroups = [ resources.ec2SecurityGroups.ssh-security-group.name ];
        keyPair = resources.ec2KeyPairs.my-key-pair.name;
      };
    };
}
