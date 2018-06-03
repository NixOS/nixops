{ system ? builtins.currentSystem, size ? "10" }:
let
  pkgs = import <nixpkgs> {};
  config = (import <nixpkgs/nixos/lib/eval-config.nix> {
    inherit system;
    modules = [ {
      fileSystems."/".device = "/dev/disk/by-label/nixos";

      boot.loader.grub.version = 2;
      boot.loader.grub.device = "/dev/sda";
      boot.loader.timeout = 0;

      services.openssh.enable = true;
      services.openssh.startWhenNeeded = false;
      services.openssh.extraConfig = "UseDNS no";

      # Patch nix to avoid problem running out of RAM when sending closures to the machine.
      # See
      #   https://github.com/NixOS/nix/issues/1681
      #   https://github.com/NixOS/nix/issues/1969
      #   https://github.com/NixOS/nixpkgs/issues/38808
      # TODO Remove when https://github.com/NixOS/nix/pull/2206 is merged and available
      nixpkgs.config.packageOverrides = pkgs: {
        nix = pkgs.nixUnstable.overrideAttrs (oldAttrs: {
          src = pkgs.fetchFromGitHub {
            owner = "NixOS";
            repo = "nix";
            rev = "54b1c596435b0aaf3a2557652ad4bf74d5756514";
            sha256 = "0g7knsfj445r50rk0d9hm5n1pv20k542bz6xf5c47qmkgvfa40x4";
          };
          patches = [
            (pkgs.fetchpatch {
              url = "https://github.com/nh2/nix/commit/d31a4410d92790e2c27110154896445d99d7abfe.patch";
              sha256 = "08gcw2xw8yc61zz2nr1j3cnd6wagp5qs02mjfazrd9wa045y26hg";
            })
          ];
          # Changes cherry-picked from upstream nix `release-common.nix` that
          # aren't in `pkgs.nixUnstable` yet:
          buildInputs = oldAttrs.buildInputs ++ [
            (pkgs.aws-sdk-cpp.override {
              apis = ["s3" "transfer"];
              customMemoryManagement = false;
            })
          ];
        });
      };
    } ];
  }).config;

in pkgs.vmTools.runInLinuxVM (
  pkgs.runCommand "libvirtd-image"
    { memSize = 768;
      preVM =
        ''
          mkdir $out
          diskImage=$out/image
          ${pkgs.vmTools.qemu}/bin/qemu-img create -f qcow2 $diskImage "${size}G"
          mv closure xchg/
        '';
      postVM =
        ''
          mv $diskImage $out/disk.qcow2
        '';
      buildInputs = [ pkgs.utillinux pkgs.perl ];
      exportReferencesGraph =
        [ "closure" config.system.build.toplevel ];
    }
    ''
      # Create a single / partition.
      ${pkgs.parted}/sbin/parted /dev/vda mklabel msdos
      ${pkgs.parted}/sbin/parted /dev/vda -- mkpart primary ext2 1M -1s

      # TODO (@Ma27) remove this entirely after NixOS 17.09 is EOLed, in
      # 18.03 `devtmpfs` is used which makes the block creation obsolete
      # (see https://github.com/NixOS/nixpkgs/commit/0d27df280f7ed502bba65e2ea13469069f9b275a)
      if [ ! -b /dev/vda1 ]; then
        . /sys/class/block/vda1/uevent
        mknod /dev/vda1 b $MAJOR $MINOR
      fi

      # Create an empty filesystem and mount it.
      ${pkgs.e2fsprogs}/sbin/mkfs.ext4 -L nixos /dev/vda1
      ${pkgs.e2fsprogs}/sbin/tune2fs -c 0 -i 0 /dev/vda1
      mkdir /mnt
      mount /dev/vda1 /mnt

      # The initrd expects these directories to exist.
      mkdir /mnt/dev /mnt/proc /mnt/sys
      mount --bind /proc /mnt/proc
      mount --bind /dev /mnt/dev
      mount --bind /sys /mnt/sys

      # Copy all paths in the closure to the filesystem.
      storePaths=$(perl ${pkgs.pathsFromGraph} /tmp/xchg/closure)

      echo "filling Nix store..."
      mkdir -p /mnt/nix/store
      set -f
      cp -prd $storePaths /mnt/nix/store/

      mkdir -p /mnt/etc/nix
      echo 'build-users-group = ' > /mnt/etc/nix/nix.conf

      # Register the paths in the Nix database.
      printRegistration=1 perl ${pkgs.pathsFromGraph} /tmp/xchg/closure | \
          chroot /mnt ${config.nix.package.out}/bin/nix-store --load-db

      # Create the system profile to allow nixos-rebuild to work.
      chroot /mnt ${config.nix.package.out}/bin/nix-env \
          -p /nix/var/nix/profiles/system --set ${config.system.build.toplevel}

      # `nixos-rebuild' requires an /etc/NIXOS.
      mkdir -p /mnt/etc/nixos
      touch /mnt/etc/NIXOS

      # `switch-to-configuration' requires a /bin/sh
      mkdir -p /mnt/bin
      ln -s ${config.system.build.binsh}/bin/sh /mnt/bin/sh

      # Generate the GRUB menu.
      ln -s vda /dev/sda
      chroot /mnt ${config.system.build.toplevel}/bin/switch-to-configuration boot

      umount /mnt/proc /mnt/dev /mnt/sys
      umount /mnt
    ''
)

