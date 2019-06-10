{

  machine1 = # Log in and add your SSH public key to /root/.ssh/authorized_keys
    { deployment.targetEnv = "libvirtd";
      deployment.libvirtd.imageDir = "/var/lib/libvirt/images";
    };

  machine2 =
    { resources, lib, ... }:
    { deployment.targetEnv = "libvirtd";
      deployment.libvirtd.imageDir = "/var/lib/libvirt/images";
      deployment.jumpHost = "root@192.168.122.113"; # Update to IP of machine1
    };
}
