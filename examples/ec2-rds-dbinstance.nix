let
  region = "us-east-1";
  accessKeyId = "AKIA...";
in
{
  network.description = "NixOps RDS Testing";

  resources.rdsDbSecurityGroups.test-rds-sg =
    {
      inherit region accessKeyId;
      groupName = "test-nixops";
      description = "testing sg for rds";
      rules = [
        {
          cidrIp = "0.0.0.0/0";
        }
      ];
    };

  resources.rdsDbInstances.test-rds-instance =
    { resources, ... }:
    {
      inherit region accessKeyId;
      id = "test-multi-az";
      instanceClass = "db.r3.large";
      allocatedStorage = 30;
      masterUsername = "administrator";
      masterPassword = "testing123";
      port = 5432;
      engine = "postgres";
      dbName = "testNixOps";
      multiAZ = true;
      securityGroups = [ resources.rdsDbSecurityGroups.test-rds-sg ];
    };
}
