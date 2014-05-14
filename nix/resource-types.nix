{
  machines = {
    pluralDisplayName = "machines";

    baseModules = import <nixpkgs/nixos/modules/module-list.nix> ++ [ ./options.nix ];
  };

  sqsQueues = {
    pluralDisplayName = "SQS queues";

    baseModules = [ ./sqs-queue.nix ./resource.nix ];
  };

  ec2KeyPairs = {
    pluralDisplayName = "EC2 keypairs";

    baseModules = [ ./ec2-keypair.nix ./resource.nix ];
  };

  sshKeyPairs = {
    pluralDisplayName = "SSH keypairs";

    baseModules = [ ./ssh-keypair.nix ./resource.nix ];
  };

  s3Buckets = {
    pluralDisplayName = "S3 buckets";

    baseModules = [ ./s3-bucket.nix ./resource.nix ];
  };

  iamRoles = {
    pluralDisplayName = "IAM roles";

    baseModules = [ ./iam-role.nix ./resource.nix ];
  };

  ec2SecurityGroups = {
    pluralDisplayName = "EC2 security groups";

    baseModules = [ ./ec2-security-group.nix ./resource.nix ];
  };

  ebsVolumes = {
    pluralDisplayName = "EBS volumes";

    baseModules = [ ./ebs-volume.nix ./resource.nix ];
  };

  elasticIPs = {
    pluralDisplayName = "EC2 elastic IP addresses";

    baseModules = [ ./elastic-ip.nix ./resource.nix ];
  };

  ec2PlacementGroups = {
    pluralDisplayName = "EC2 placement groups";

    baseModules = [ ./ec2-placement-group.nix ./resource.nix ];
  };
}
