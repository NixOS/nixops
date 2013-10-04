{ securityGroup, ... }:
let
  region = "us-east-1";
in
{
  resources.ec2KeyPairs.my-key-pair =
    { inherit region; };

  machine =
    { resources, ... }:
    {
      deployment.targetEnv = "ec2";
      deployment.ec2 = {
        inherit region;
        instanceType = "m1.small";
        securityGroups = [ securityGroup ];
        keyPair = resources.ec2KeyPairs.my-key-pair.name ;
      };
    };
}
