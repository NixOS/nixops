{
  vbox =
    { deployment.targetEnv = "virtualbox"; };

  machine =
    { resources, ... }:
    { deployment.targetEnv = "container";
      deployment.container.host = resources.machines.vbox;
    };
}
