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
      let
        nixosVersion = builtins.substring 0 5 (config.system.nixos.version or config.system.nixosVersion);
        images =
          let
            p = pkgs.path + "/nixos/modules/virtualisation/virtualbox-images.nix";
            self = rec {
              "16.09" = { url = "http://nixos.org/releases/nixos/virtualbox-nixops-images/virtualbox-nixops-16.09.877.5b08a40.vmdk.xz"; sha256 = "c20ee9ff0f58b10cd2b1e52411a56a862c8eaecddbbddd337ae0cca888f6727f"; };
              "17.03" = self."16.09";
              "17.09" = self."16.09";
              "18.03" = { url = "http://nixos.org/releases/nixos/virtualbox-nixops-images/virtualbox-nixops-18.03pre131587.b6ddb9913f2.vmdk.xz"; sha256 = "1hxdimjpndjimy40g1wh4lq7x0d78zg6zisp23cilqr7393chnna"; };
              "18.09" = { url = "http://nixos.org/releases/nixos/virtualbox-nixops-images/virtualbox-nixops-18.09.2211.19a0543c628.vmdk.xz"; sha256 = "f37799b99f430ede872b17f4485f950b667ab7f9c7a75fe25b3cdd3aa7518f10"; };
              "19.03" = { url = "http://nixos.org/releases/nixos/virtualbox-nixops-images/virtualbox-nixops-19.03.172205.ea497998e4b.vmdk.xz"; sha256 = "2f18b22978d779995bcf0d076f88447a90a8e5364d384cac7fa6d20e9b4050c6"; };
              latest = self."19.03";
            };
          in if builtins.pathExists p then import p else self;
      in
      { port = 0;
        size = mkDefault 0;
        baseImage = mkDefault (
          let
            unpack = version: pkgsNative.runCommand "virtualbox-nixops-${version}.vmdk" { preferLocalBuild = true; allowSubstitutes = false; }
              ''
                xz -d < ${pkgsNative.fetchurl (images."${version}" or images.latest)} > $out
              '';
          in if config.nixpkgs.system == "x86_64-linux" then
            unpack nixosVersion
          else
            throw "Unsupported VirtualBox system type!"
        );
      };
  };

}
