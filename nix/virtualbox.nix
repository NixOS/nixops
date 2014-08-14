{ config, pkgs, lib ? pkgs.lib, ... }:

with lib;

let

  # Do the fetching and unpacking of the VirtualBox guest image
  # locally so that it works on non-Linux hosts.
  pkgsNative = import <nixpkgs> { system = builtins.currentSystem; };

  cfg = config.deployment.virtualbox;

in

{

  ###### interface

  options = {

    deployment.virtualbox.memorySize = mkOption {
      default = 512;
      type = types.int;
      description = ''
        Memory size (M) of virtual machine.
      '';
    };

    deployment.virtualbox.headless = mkOption {
      default = false;
      description = ''
        If set, the VirtualBox instance is started in headless mode,
        i.e., without a visible display on the host's desktop.
      '';
    };

    deployment.virtualbox.disks = mkOption {
      default = {};
      example =
        { big-disk = {
            port = 1;
            size = 1048576;
          };
        };
      type = types.attrsOf types.optionSet;
      description = "Definition of the virtual disks attached to this instance.";

      options = {

        port = mkOption {
          example = 1;
          type = types.int;
          description = "SATA port number to which the disk is attached.";
        };

        size = mkOption {
          type = types.int;
          description = "Size (in megabytes) of this disk.";
        };

        baseImage = mkOption {
          default = null;
          example = "/home/alice/base-disk.vdi";
          type = types.nullOr types.path;
          description = ''
            If set, this disk is created as a clone of the specified
            disk image (and the <literal>size</literal> attribute is
            ignored).
          '';
        };

      };
    };

    deployment.virtualbox.sharedFolders = mkOption {
      default = {};

      example =
        { home = {
            hostPath = "/home";
            readOnly = false;
          };
        };

      type = types.attrsOf types.optionSet;

      description = ''
        Definition of the host folders that should be shared with this instance.
      '';

      options = {

        hostPath = mkOption {
          example = "/home";
          type = types.str;
          description = ''
            The path of the host directory that should be shared to the guest
          '';
        };

        readOnly = mkOption {
          type = types.bool;
          default = true;
          description = ''
            Specifies if the shared folder should be read-only for the guest
          '';
        };

      };
    };

  };


  ###### implementation

  config = mkIf (config.deployment.targetEnv == "virtualbox") {

    nixpkgs.system = mkOverride 900 "x86_64-linux";

    # Add vboxsf support to initrd to support booting from
    # shared folders
    boot.initrd = mkIf (cfg.sharedFolders != {}) {
      kernelModules = [ "vboxsf" ];

      extraUtilsCommands = ''
        cp -v ${pkgs.linuxPackages.virtualboxGuestAdditions}/sbin/mount.vboxsf \
          $out/bin/
      '';
    };

    deployment.virtualbox.disks.disk1 =
      { port = 0;
        size = 0;
        baseImage = mkDefault (
          let
            unpack = name: sha256: pkgsNative.runCommand "virtualbox-nixops-${name}.vdi" {}
              ''
                xz -d < ${pkgsNative.fetchurl {
                  url = "http://nixos.org/releases/nixos/virtualbox-nixops-images/virtualbox-nixops-${name}.vdi.xz";
                  inherit sha256;
                }} > $out
              '';
          in if config.nixpkgs.system == "x86_64-linux" then
            unpack "14.04.371.735bfb9" "252ae9279dd67d199400e9d4d41b3bd95550fb23a09164f645ed594ddde2578c"
          else
            throw "Unsupported VirtualBox system type!"
        );
      };
  };

}
