{
  machine =
    { deployment.targetEnv = "libvirtd";
      deployment.libvirtd.imageDir = "/var/lib/libvirt/images";
    };
}
