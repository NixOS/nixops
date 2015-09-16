let
  region = "us-east-1";
in
{
  network.description = "NixOps Test";

  resources.rdsDbInstances.test-rds-instance = {
    inherit region;
    id = "myOtherDatabaseIsAFilesystem";
    instanceClass = "db.r3.large";
    allocatedStorage = 30;
    masterUsername = "administrator";
    masterPassword = "testing123";
    port = 5432;
    engine = "postgres";
    dbName = "helloDarling";
  };
}
