let
  accessKeyId = builtins.getEnv "NIXOPS_TEST_ACCESS_KEY_ID";
  vpcId = builtins.getEnv "NIXOPS_TEST_VPC_ID";
  region = builtins.getEnv "NIXOPS_TEST_REGION";
in
{
  resources.ec2SecurityGroups.nixops-test = {
    inherit accessKeyId region vpcId;
    description = "Testing NixOps extensions to create security groups inside VPC";
    rules = [ {
      fromPort = 22;
      toPort = 22;
      sourceIp = "0.0.0.0/0";
    } ];
  };
}
