{ config, pkgs, lib, ... }:

with lib;

let
  libvirt_image_helpers = import ./libvirtd-image.nix;
  sz = toString config.deployment.libvirtd.baseImageSize;
  ssh_pubkey = builtins.getEnv "NIXOPS_LIBVIRTD_PUBKEY";

  base_config = libvirt_image_helpers.base_image_config // {
    services.openssh.enable = true;
    services.openssh.startWhenNeeded = false;
    services.openssh.extraConfig = "UseDNS no";
  };

  ssh_image = if config.deployment.libvirtd.boot_config == null then
    let base_image = libvirt_image_helpers.create_nixos_image {
          size = sz;
          config = base_config;
        };

    in libvirt_image_helpers.edit_image {
      inherit pkgs base_image;
      cmd = ''
        mkdir -p /mnt/etc/ssh/authorized_keys.d
        echo '${ssh_pubkey}' > /mnt/etc/ssh/authorized_keys.d/root
      '';
    }

  else
    libvirt_image_helpers.create_nixos_image {
      inherit pkgs;
      size = sz;
      config.imports = [
        base_config
        { users.users.root.openssh.authorizedKeys.keys = [ ssh_pubkey ]; }
        config.deployment.libvirtd.boot_config
      ];
    }

  ;

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

    deployment.libvirtd.boot_config = mkOption {
      default = null;
      example = {
        networking = {
          interfaces.enp0s2.ip4 = [ { address = "10.0.0.2"; prefixLength = 24; } ];
          defaultGateway = "10.0.0.1";
        };
      };
      type = types.nullOr types.attrs;
      description = ''
        NixOS configuration needed for the first image to boot and be reachable via ssh.
        This will be used only during image bootstrapping.
        Leave null to use default configuration, which uses DHCP.
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
  };

  ###### implementation

  config = mkIf (config.deployment.targetEnv == "libvirtd") (base_config // {
    deployment.libvirtd.baseImage = mkDefault ssh_image;
    nixpkgs.system = mkOverride 900 "x86_64-linux";
    deployment.hasFastConnection = true;
  });

}
