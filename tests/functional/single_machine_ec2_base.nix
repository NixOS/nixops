{ privateKey, keyPair, securityGroup }:

{
  machine.deployment = {
    targetEnv = "ec2";

    ec2 = {
      region = "us-east-1";

      instanceType = "m1.small";

      inherit privateKey keyPair;

      securityGroups = [ securityGroup ];
    };
  };
}
