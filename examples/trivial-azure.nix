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
    };
}