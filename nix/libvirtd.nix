{ config, pkgs, lib, ... }:

with lib;

let
  sz = toString config.deployment.libvirtd.baseImageSize;
  base_image = import ./libvirtd-root-image.nix { size = sz; };
  the_key = builtins.getEnv "NIXOPS_LIBVIRTD_PUBKEY";
  ssh_image = pkgs.vmTools.runInLinuxVM (
    pkgs.runCommand "libvirtd-ssh-image"
      { memSize = 768;
        preVM =
          ''
            mkdir $out
            diskImage=$out/image
            ${pkgs.vmTools.qemu}/bin/qemu-img create -f qcow2 -b ${base_image}/disk.qcow2 $diskImage
          '';
        buildInputs = [ pkgs.utillinux ];
        postVM =
          ''
            mv $diskImage $out/disk.qcow2
          '';
      }
      ''
        . /sys/class/block/vda1/uevent
        mknod /dev/vda1 b $MAJOR $MINOR
        mkdir /mnt
        mount /dev/vda1 /mnt

        mkdir -p /mnt/etc/ssh/authorized_keys.d
        echo '${the_key}' > /mnt/etc/ssh/authorized_keys.d/root
        umount /mnt
      ''
  );
in

{

  ###### interface

  options = {
    deployment.libvirtd.imageDir = mkOption {
      type = types.path;
      default = "/var/lib/libvirt/images";
      description = ''
        Directory to store VM image files. Note that it should be writable both by you and by libvirtd daemon.
      '';
    };

    deployment.libvirtd.memorySize = mkOption {
      default = 512;
      type = types.int;
      description = ''
        Memory size (M) of virtual machine.
      '';
    };

    deployment.libvirtd.headless = mkOption {
      default = false;
      description = ''
        If set VM  is started in headless mode,
        i.e., without a visible display on the host's desktop.
      '';
    };

    deployment.libvirtd.baseImageSize = mkOption {
      default = 10;
      type = types.int;
      description = ''
        The size (G) of base image of virtual machine.
      '';
    };

    deployment.libvirtd.baseImage = mkOption {
      default = null;
      example = "/home/alice/base-disk.qcow2";
      type = with types; nullOr path;
      description = ''
        The disk is created using the specified
        disk image as a base.
      '';
    };

    deployment.libvirtd.networks = mkOption {
      default = [ "default" ];
      type = types.listOf types.str;
      description = "Names of libvirt networks to attach the VM to.";
    };

    deployment.libvirtd.extraDevicesXML = mkOption {
      default = "";
      type = types.str;
      description = "Additional XML appended at the end of device tag in domain xml. See https://libvirt.org/formatdomain.html";
    };

    deployment.libvirtd.disks = mkOption {
      default = {};
      example =
        { big-disk = {
            device = "hdb";
            size = 1048576;
          };
        };
      type = types.attrsOf types.optionSet;
      description = ''
        Definition of the disk images attached to this domain.  If baseImage is not provided then a
        disk image containing a single EXT4 partition will be created.  The name of this option set
        will be the label of the created EXT4 partition.
      '';

      options = {
        device = mkOption {
          type = types.string;
          description = "IDE device the disk will be attached to.";
        };

        size = mkOption {
          type = types.int;
          description = "Size (in megabytes) of this disk.";
        };

        baseImage = mkOption {
          default = null;
          example = "/home/alice/another-disk.qcow2";
          type = with types; nullOr path;
          description = ''
            The image to use as the base of the device image. If no baseImage path is set then a disk
            image contianing a single EXT4 partition will be created.
          '';
        };
      };
    };
  };

  ###### implementation

  config = mkIf (config.deployment.targetEnv == "libvirtd") {
    deployment.libvirtd.baseImage = mkDefault ssh_image;

    nixpkgs.system = mkOverride 900 "x86_64-linux";

    fileSystems."/".device = "/dev/disk/by-label/nixos";

    boot.loader.grub.version = 2;
    boot.loader.grub.device = "/dev/sda";
    boot.loader.grub.timeout = 0;

    services.openssh.enable = true;
    services.openssh.startWhenNeeded = false;
    services.openssh.extraConfig = "UseDNS no";
  };

}
