{ config, pkgs, lib, ... }:

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

    deployment.virtualbox.vmFlags = mkOption {
      default = [];
      type = types.listOf types.string;
      description = ''
        Arbitrary string arguments to append to the modifyvm command.
      '';
    };

    deployment.virtualbox.vcpu = mkOption {
      default = null;
      type = types.nullOr types.int;
      description = ''
        Number of Virtual CPUs.  Left unspecified if not provided.
      '';
    };

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
      description = ''
        Definition of the virtual disks attached to this instance.
        The root disk is called <option>deployment.virtualbox.disks.disk1</option>.
      '';
      type = with types; attrsOf (submodule {
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
              disk image.
            '';
          };

        };

      });
    };

    deployment.virtualbox.sharedFolders = mkOption {
      default = {};

      example =
        { home = {
            hostPath = "/home";
            readOnly = false;
          };
        };

      description = ''
        Definition of the host folders that should be shared with this instance.
      '';

      type = with types; attrsOf (submodule {

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
      });
    };

  };


  ###### implementation

  config = mkIf (config.deployment.targetEnv == "virtualbox") {

    nixpkgs.system = mkOverride 900 "x86_64-linux";

    deployment.hasFastConnection = true;

    # Add vboxsf support to initrd to support booting from
    # shared folders
    boot.initrd = mkIf (cfg.sharedFolders != {}) {
      kernelModules = [ "vboxsf" ];

      extraUtilsCommands = ''
        cp -v ${pkgs.linuxPackages.virtualboxGuestAdditions}/bin/mount.vboxsf \
          $out/bin/
      '';
    };

    deployment.virtualbox.disks.disk1 =
      { port = 0;
        size = mkDefault 0;
        baseImage = mkDefault (
          let
            unpack = name: sha256: pkgsNative.runCommand "virtualbox-nixops-${name}.vmdk" { preferLocalBuild = true; allowSubstitutes = false; }
              ''
                xz -d < ${pkgsNative.fetchurl {
                  url = "http://nixos.org/releases/nixos/virtualbox-nixops-images/virtualbox-nixops-${name}.vmdk.xz";
                  inherit sha256;
                }} > $out
              '';
          in if config.nixpkgs.system == "x86_64-linux" then
            unpack "16.09.877.5b08a40" "c20ee9ff0f58b10cd2b1e52411a56a862c8eaecddbbddd337ae0cca888f6727f"
          else
            throw "Unsupported VirtualBox system type!"
        );
      };
  };

}
