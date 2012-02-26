let

  config =
    { deployment.targetEnv = "virtualbox";
    };

in

{
  proxy = config;
  backend1 = config;
  backend2 = config;
}
