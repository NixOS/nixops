let
  region = "us-east-1";
in
{
  network.description = "NixOps Test";

  resources.rdsDbInstances.test-rds-instance =
    { resources, ... }:
    {
      inherit region;
      id = "myOtherDatabaseIsAFilesystem";
      instanceClass = "db.r3.large";
      allocatedStorage = 30;
      masterUsername = "administrator";
      masterPassword = "testing123";
      port = 5432;
      engine = "postgres";
      dbName = "helloDarling";
      vpcSecurityGroups = [ resources.ec2SecurityGroups.test-rds-sg ];
    };

  resources.ec2SecurityGroups.test-rds-sg =
    {
      inherit region;
      description = "testing sg for rds";
      rules = [
        { toPort = 5432; fromPort = 5432; sourceIp = "0.0.0.0/0"; }
      ];
    };
}
