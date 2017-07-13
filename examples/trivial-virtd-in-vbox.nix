{
  vbox =
    {
      deployment.targetEnv = "virtualbox";
      virtualisation.libvirtd.enable = true;
      networking.firewall.checkReversePath = false;

      users.users.libvirtd_master = {
        extraGroups = [ "libvirtd" ];
        openssh.authorizedKeys.keys = [ "my-ssh-public-key" ];
      };
      system.activationScripts.createLibvirtdImageDir = {
        text = ''
          mkdir -p /var/lib/libvirtd/images
          chown libvirtd_master:libvirtd /var/lib/libvirtd/images
        '';
        deps = [];
      };
    };

  machine =
    { resources, ... }:
    { deployment.targetEnv = "libvirtd";
      deployment.libvirtd.host = resources.machines.vbox;
      deployment.libvirtd.remote_user = "libvirtd_master";
      deployment.libvirtd.headless = true;
    };
}

