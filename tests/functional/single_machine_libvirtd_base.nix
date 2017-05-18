{
  machine =
    { resources, ... }:
    {
      deployment.targetEnv = "libvirtd";
      deployment.libvirtd = {
        headless = true;
      };
    };
}
