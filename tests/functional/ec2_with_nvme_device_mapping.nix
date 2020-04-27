let
  region = "us-east-1";
  zone = "us-east-1c";
in
{
  network.description = "NixOps Test";

  resources.ebsVolumes.foo-disk = {
    inherit region zone;
    size = 5;
    tags = {
      Name = "My NixOps Test Foo Disk";
    };
  };

  resources.ec2KeyPairs.my-key-pair =
    { inherit region; };

  resources.ec2SecurityGroups.ssh-security-group = {
    inherit region;
    description = "Security group for NixOps tests";
    rules = [ {
      fromPort = 22;
      toPort = 22;
      sourceIp = "0.0.0.0/0";
    } ];
  };

  machine =
    { resources, pkgs, ... }:
    {
      deployment.targetEnv = "ec2";
      deployment.ec2 = {
        inherit region zone;
        ebsBoot = true;
        instanceType = "c5.large";
        securityGroups = [ resources.ec2SecurityGroups.ssh-security-group ];

        keyPair = resources.ec2KeyPairs.my-key-pair;
      };

      fileSystems."/data" = {
        autoFormat = true;
        fsType = "ext4";
        device = "/dev/nvme1n1";
        ec2.disk = resources.ebsVolumes.foo-disk;
      };
    };
}
