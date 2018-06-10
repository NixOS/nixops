{
  machine1 = {
    deployment.targetEnv = "virtualbox";
    deployment.encryptedLinksTo = [ "machine2" ];
    deployment.virtualbox.headless = true;
  };

  machine2 = {
    deployment.targetEnv = "virtualbox";
    deployment.encryptedLinksTo = [ "machine1" ];
    deployment.virtualbox.headless = true;
  };
}
