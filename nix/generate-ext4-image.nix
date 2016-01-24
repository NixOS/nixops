{ system ? builtins.currentSystem
, name ? "none"
, size ? 10 }:
let
  pkgs = import <nixpkgs> {};
  config = (import <nixpkgs/nixos/lib/eval-config.nix> {
    inherit system;
    modules = [ {
      fileSystems."/".device = "/dev/disk/by-label/nixos";

      boot.loader.grub.version = 2;
      boot.loader.grub.device = "/dev/sda";
      boot.loader.grub.timeout = 0;

      services.openssh.enable = true;
      services.openssh.startWhenNeeded = false;
      services.openssh.extraConfig = "UseDNS no";
    } ];
  }).config;

in pkgs.vmTools.runInLinuxVM (
  pkgs.runCommand "libvirtd-image"
    { memSize = 768;
      preVM =
        ''
          mkdir $out
          diskImage=$out/image
          ${pkgs.vmTools.qemu}/bin/qemu-img create -f qcow2 $diskImage "${toString size}M"
        '';
      postVM =
        ''
          mv $diskImage $out/disk.qcow2
        '';
      buildInputs = [ pkgs.utillinux pkgs.perl ];
    }
    ''
      # Create a single / partition.
      ${pkgs.parted}/sbin/parted /dev/vda mklabel msdos
      ${pkgs.parted}/sbin/parted /dev/vda -- mkpart primary ext2 1M -1s
      . /sys/class/block/vda1/uevent
      mknod /dev/vda1 b $MAJOR $MINOR

      # Create an empty filesystem
      ${pkgs.e2fsprogs}/sbin/mkfs.ext4 -L ${name} /dev/vda1
      ${pkgs.e2fsprogs}/sbin/tune2fs -c 0 -i 0 /dev/vda1
    ''
)
