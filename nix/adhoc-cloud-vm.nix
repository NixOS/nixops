{ config, pkgs, ... }:

with pkgs.lib;

{
  boot.loader.grub.version = 2;
  boot.loader.grub.device = "/dev/vda";
  boot.initrd.kernelModules = [ "virtio_blk" "virtio_pci" ];

  fileSystems =
    [ { mountPoint = "/";
        label = "nixos";
      }
    ];

  swapDevices = [ { label = "swap"; } ];

  networking.hostName = mkOverride 950 "";

  services.openssh.enable = true;

  services.mingetty.ttys = [ "hvc0" "tty1" "tty2" ];
}
