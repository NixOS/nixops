{
  machine =
    { deployment.targetEnv = "libvirtd";
      deployment.libvirtd.headless = true;
      deployment.libvirtd.targetHost = "my.machine.net";
    };
}
