{
  libvirtd = { ... }:
    { deployment.targetEnv = "libvirtd";
    };

  container = { pkgs, resources, ... }:
    { deployment.targetEnv = "container";
      deployment.container.host = resources.machines.libvirtd;
      deployment.container.localAddress = "10.235.1.2";
      deployment.container.hostAddress = "10.235.1.1";

      environment.systemPackages = [ pkgs.hello ];
    };
}
