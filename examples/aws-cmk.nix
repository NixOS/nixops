{
    resources.cmk.cmkTest = {
      alias = "nixops-kms-test-2";
      #policy =
      description = "nixops is the best";
      origin = "AWS_KMS";
      deletionWaitPeriod = 7;
      region = "us-east-1";
      accessKeyId = "testing";
      tags = { hello = "hello";};
    };
}
