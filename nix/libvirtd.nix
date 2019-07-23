{ config, pkgs, lib, ... }:

with lib;

let
  the_key = builtins.getEnv "NIXOPS_LIBVIRTD_PUBKEY";
  ssh_image = import <nixpkgs/nixos/lib/make-disk-image.nix> {
    name = "libvirtd-ssh-image";
    format = "qcow2";
    diskSize = config.deployment.libvirtd.baseImageSize * 1024;
    config = config;
    contents = [{
      source = (pkgs.writeText "authorized_keys.d-root" the_key);
      target = "/etc/ssh/authorized_keys.d/root";
    }];
    lib = pkgs.lib;
    inherit pkgs;
  };
in

{

  ###### interface

  options = {
    deployment.libvirtd.storagePool = mkOption {
      type = types.str;
      default = "default";
      description = ''
        The storage pool where the virtual disk is be created.
      '';
    };

    deployment.libvirtd.URI = mkOption {
      type = types.str;
      default = "qemu:///system";
      description = ''
        Connection URI.
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
      description = "Names of libvirt networks to attach the VM to.";
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

    deployment.libvirtd.domainType = mkOption {
      default = "kvm";
      type = types.str;
      description = "Specify the type of libvirt domain to create (see '$ virsh capabilities | grep domain' for valid domain types";
    };

    deployment.libvirtd.cmdline = mkOption {
      default = "";
      type = types.str;
      description = "Specify the kernel cmdline (valid only with the kernel setting).";
    };

    deployment.libvirtd.initrd = mkOption {
      default = "";
      type = types.str;
      description = "Specify the kernel initrd (valid only with the kernel setting).";
    };

    deployment.libvirtd.kernel = mkOption {
      default = "";
      type = types.str; # with types; nullOr path;
      description = "Specify the host kernel to launch (valid for kvm).";
    };
  };

  ###### implementation

  config = mkIf (config.deployment.targetEnv == "libvirtd") {
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
