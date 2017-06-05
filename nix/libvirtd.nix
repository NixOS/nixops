{ config, pkgs, lib, ... }:

with lib;

let
  sz = toString config.deployment.libvirtd.baseImageSize;
  base_image = import ./libvirtd-image.nix { size = sz; };
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

  interfaceOpts = {
    options = {
      type = mkOption {
        type = types.str;
        default = "network";
        example = "bridge";
        description = ''
          Type of the interface.
        '';
      };

      name = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = ''
          Name of the libvirt network or of the bridge interface.
          Ignored if type is not 'network' or 'bridge'.
        '';
      };

      mac = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = ''
          MAC address of the interface. Leave empty to let libvirt choose it.
        '';
      };

      extraXML = mkOption {
        type = types.str;
        default = "";
        example = "<model type='rtl8139'/>";
        description = ''
          Additional XML configuration of the interface. See https://libvirt.org/formatdomain.html
        '';
      };
    };
  };
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

    deployment.libvirtd.vcpu = mkOption {
      default = 1;
      type = types.int;
      description = ''
        Number of Virtual CPUs.
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
      description = ''
        Names of libvirt networks to attach the VM to.
        Shortcut for adding network interfaces to deployment.libvirtd.interfaces
      '';
    };

    deployment.libvirtd.privateIPv4 = mkOption {
      default = "dhcp";
      example = "10.1.2.3";
      type = types.str;
      description = ''
        IP to use to ssh into the machine.
        Put 'dhcp' to let nixops get the IP from libvirt's dhcp (works with default libvirt network);
        put 'arp' to let nixops detect IP in the host's ARP table (works with most setups)
      '';
    };

    deployment.libvirtd.interfaces = mkOption {
      default = [];
      example = [
        { type = "network"; name = "default"; mac = "00:11:22:33:44:55"; }
        { type = "bridge"; name = "br0"; extraXML = ''<model type='rtl8139'/>''; }
      ];
      type = types.listOf (types.submodule interfaceOpts);
      apply = interfaces:
        let ifacexml = i: ''
              <interface type="${i.type}">
                ${optionalString (i.type == "network" && i.name != null) ''<source network="${i.name}"/>''}
                ${optionalString (i.type == "bridge" && i.name != null) ''<source bridge="${i.name}"/>''}
                ${optionalString (i.mac != null) ''<mac address="${i.mac}"/>''}
                ${i.extraXML}
              </interface>
            '';
        in map ifacexml interfaces;
      description = "Configuration for each network interface to attach the VM to.";
    };

    deployment.libvirtd.extraDevicesXML = mkOption {
      default = "";
      type = types.str;
      description = "Additional XML appended at the end of device tag in domain xml. See https://libvirt.org/formatdomain.html";
    };

    deployment.libvirtd.extraDomainXML = mkOption {
      default = "";
      type = types.str;
      description = "Additional XML appended at the end of domain xml. See https://libvirt.org/formatdomain.html";
    };
  };

  ###### implementation

  config = mkIf (config.deployment.targetEnv == "libvirtd") {
    deployment.libvirtd.interfaces = map (name: { type = "network"; inherit name; }) config.deployment.libvirtd.networks;
    deployment.libvirtd.baseImage = mkDefault ssh_image;

    nixpkgs.system = mkOverride 900 "x86_64-linux";

    fileSystems."/".device = "/dev/disk/by-label/nixos";

    boot.loader.grub.version = 2;
    boot.loader.grub.device = "/dev/sda";
    boot.loader.timeout = 0;

    services.openssh.enable = true;
    services.openssh.startWhenNeeded = false;
    services.openssh.extraConfig = "UseDNS no";

    deployment.hasFastConnection = true;
  };

}
