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
      securityGroups = [ resources.rdsDbSecurityGroups.test-rds-sg ];
    };

  resources.rdsDbSecurityGroups.test-rds-sg =
    {
      inherit region;
      groupName = "test-nixops";
      description = "testing sg for rds";
      rules = [
        {
          cidrIp = "0.0.0.0/0";
        }
      ];
    };

}
