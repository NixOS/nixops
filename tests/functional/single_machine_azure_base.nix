{
  machine =
    { resources, ...}:  {
      deployment.targetEnv = "azure";
      deployment.azure = {
        location = "westus";
        size = "Standard_A0"; # minimal size that supports load balancing
      };
    };
}