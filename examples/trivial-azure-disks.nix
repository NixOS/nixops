let

  # change this as necessary or leave empty and use ENV vars
  credentials = {
  };

in {
  machine =
    { resources, ...}:  {
      deployment.targetEnv = "azure";
      deployment.azure = credentials // {
        location = "westus";
        size = "Standard_A0"; # minimal size that supports load balancing
      };

      # create a data disk, format it as ext4, mount as /crypt
      fileSystems."/crypt" = {
        autoFormat = true;
        fsType = "ext4";
        azure.lun = 0;
        azure.size = 5;
        # encrypt the disk with a random passphrase
        azure.encrypt = true;
      };
    };
}