let

  config =
    { deployment.targetEnv = "adhoc";
      deployment.adhoc.controller = "root@stan.nixos.org";
    };

in

{
  proxy = config;
  backend1 = config;
  backend2 = config;
}
