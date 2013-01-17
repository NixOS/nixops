{
  machine =
    { deployment.targetEnv = "virtualbox";
      #deployment.virtualbox.headless = true;
      deployment.virtualbox.disks.big-disk =
        { port = 1;
          size = 2048;
        };
      deployment.virtualbox.disks.small-disk =
        { port = 2;
          size = 128;
        };
    };
}
