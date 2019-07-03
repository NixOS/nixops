{
    resources.cmk.cmk =
    {lib, ...}:
    {
      alias = "nixops-kms";
      description = "nixops is the best";
      policy = builtins.toJSON
      {
        Statement= [
          {
              Effect= "Allow";
              Principal = "*";
              Action = "*";
              Resource= "*";
          }
        ];
      };
      origin = "AWS_KMS";
      deletionWaitPeriod = 7;
      region = "us-east-1";
      accessKeyId = "testing";
      tags = { name = "nixops-managed-cmk";};
    };
    resources.ebsVolumes.ebs =
    {resources, ...}:
    {
      region = "us-east-1";
      accessKeyId = "testing";
      size = 50;
      volumeType = "gp2";
      kmsKeyId = resources.cmk.cmk;
      zone = "us-east-1a";
      tags = { name = "nixops"; env = "test";};
  };

}
