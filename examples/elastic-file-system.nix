let
  region = "eu-west-1";
  accessKeyId = "eelco";
  subnet = "subnet-14930963";
in

{

  resources.ec2KeyPairs.default =
    { inherit region accessKeyId;
    };

  resources.elasticFileSystems.filesystem =
    { inherit region accessKeyId;
      tags.Name = "My Test FS";
    };

  resources.elasticFileSystemMountTargets.test-mount =
    { resources, ... }:
    { inherit region accessKeyId subnet;
      fileSystem = resources.elasticFileSystems.filesystem;
      securityGroups = [ "default" ];
    };

  machine =
    { config, pkgs, resources, ... }:
    { deployment.targetEnv = "ec2";
      deployment.ec2.instanceType = "t2.large";
      deployment.ec2.region = region;
      deployment.ec2.accessKeyId = accessKeyId;
      deployment.ec2.securityGroups = [ "default" ];
      deployment.ec2.subnetId = subnet;
      deployment.ec2.associatePublicIpAddress = true;
      deployment.ec2.securityGroupIds = [ "default" ];
      deployment.ec2.keyPair = resources.ec2KeyPairs.default;
      deployment.ec2.tags.Name = "EFS test";
      boot.supportedFilesystems = [ "nfs4" ];

      fileSystems."/efs" =
        { fsType = "nfs";
          device = "${resources.elasticFileSystemMountTargets.test-mount.ipAddress}:/";
          options = [ "nfsvers=4.1" ];
        };
    };

}
