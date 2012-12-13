{
  machine =
    { deployment.targetEnv = "virtualbox";
      #deployment.virtualbox.headless = true;
      deployment.virtualbox.disks.big-disk =
        { port = 1;
          device = 0; # default
          size = 2048;
        };
    };
}
