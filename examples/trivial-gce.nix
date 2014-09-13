{
  machine =
    { deployment.targetEnv = "gce";
      deployment.gce = {
        # credentials
        project = "...";
        serviceAccount = "...@developer.gserviceaccount.com";
        accessKey = "/path/to/your.pem";

        # instance properties
        region = "europe-west1-b";
        instanceType = "n1-standard-2";
        tags = ["crazy"];
        scheduling.automaticRestart = true;
        scheduling.onHostMaintenance = "MIGRATE";
      } ;

      fileSystems."/data"=
        { autoFormat = true;
          fsType = "ext4";
          gce.size = 10;
          gce.encrypt = true;
          gce.disk_name = "data";
        };
    };
}
