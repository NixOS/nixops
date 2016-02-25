let

  # change this as necessary or leave empty and use ENV vars
  credentials = {
  };

  azure = { backendAddressPools ? [] }: { resources, ...}:  {
    deployment.targetEnv = "azure";
    deployment.azure = credentials // {
      location = "westus";
      size = "Standard_A0"; # minimal size that supports load balancing
      availabilitySet = resources.azureAvailabilitySets.set;
      networkInterfaces.default.backendAddressPools = backendAddressPools;
    };
  };

  azure_backend = {resources, ...}@args:
    azure { backendAddressPools = [{loadBalancer = resources.azureLoadBalancers.lb;}]; } args;

in {

  resources.azureReservedIPAddresses.lb-ip = credentials // {
    location = "West US";
  };

  resources.azureAvailabilitySets.set = credentials // {
    location = "westus";
  };

  resources.azureLoadBalancers.lb = {resources,...}: credentials // {
    location = "westus";
    frontendInterfaces.default.publicIpAddress = resources.azureReservedIPAddresses.lb-ip;
    loadBalancingRules.web = {
      frontendPort = 80;
      backendPort = 80;
    };
  };

  proxy    = azure {};
  backend1 = azure_backend;
  backend2 = azure_backend;

}
