let
  makeconfig = { system, config }:
    (import <nixpkgs/nixos/lib/eval-config.nix> {
      inherit system;
      modules = [ config ];
    }).config;

in rec {
  base_image_config = {
    fileSystems."/".device = "/dev/disk/by-label/nixos";

    boot.loader.grub.version = 2;
    boot.loader.grub.device = "/dev/sda";
    boot.loader.timeout = 0;
  };


  create_nixos_image = {
    system ? builtins.currentSystem,
    pkgs ? import <nixpkgs> {},
    size ? "10",
    config ? base_image_config
  }:
  let
    cfg = makeconfig { inherit system config; };

  in pkgs.vmTools.runInLinuxVM (
    # TODO: Use <nixpkgs/nixos/lib/make-disk-image.nix> when
    # https://github.com/NixOS/nixpkgs/issues/20471 is fixed
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
          [ "closure" cfg.system.build.toplevel ];
      }
      ''
        # Create a single / partition.
        ${pkgs.parted}/sbin/parted /dev/vda mklabel msdos
        ${pkgs.parted}/sbin/parted /dev/vda -- mkpart primary ext2 1M -1s
        . /sys/class/block/vda1/uevent
        mknod /dev/vda1 b $MAJOR $MINOR

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
            chroot /mnt ${cfg.nix.package.out}/bin/nix-store --load-db

        # Create the system profile to allow nixos-rebuild to work.
        chroot /mnt ${cfg.nix.package.out}/bin/nix-env \
            -p /nix/var/nix/profiles/system --set ${cfg.system.build.toplevel}

        # `nixos-rebuild' requires an /etc/NIXOS.
        mkdir -p /mnt/etc/nixos
        touch /mnt/etc/NIXOS

        # `switch-to-configuration' requires a /bin/sh
        mkdir -p /mnt/bin
        ln -s ${cfg.system.build.binsh}/bin/sh /mnt/bin/sh

        # Generate the GRUB menu.
        ln -s vda /dev/sda
        chroot /mnt ${cfg.system.build.toplevel}/bin/switch-to-configuration boot

        umount /mnt/proc /mnt/dev /mnt/sys
        umount /mnt
      ''
  );


  edit_image = {
    pkgs ? import <nixpkgs> {},
    base_image,
    cmd
  }:
    pkgs.vmTools.runInLinuxVM (
      pkgs.runCommand "libvirtd-edit-image"
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

          ${cmd}

          umount /mnt
        ''
    );


  deploy_in_nixos_image = {
    system ? builtins.currentSystem,
    pkgs ? import <nixpkgs> {},
    base_image,
    config
  }:
    let
      cfg = makeconfig { inherit system config; };

    in pkgs.vmTools.runInLinuxVM (
      pkgs.runCommand "libvirtd-deploy-in-nixos-image"
        { memSize = 768;
          preVM =
            ''
              mkdir $out
              diskImage=$out/image
              ${pkgs.vmTools.qemu}/bin/qemu-img create -f qcow2 -b ${base_image}/disk.qcow2 $diskImage
              mv closure xchg/
            '';
          postVM =
            ''
              mv $diskImage $out/disk.qcow2
            '';
          buildInputs = [ pkgs.utillinux pkgs.perl ];
          exportReferencesGraph =
            [ "closure" cfg.system.build.toplevel ];
        }
        ''
          . /sys/class/block/vda1/uevent
          mknod /dev/vda1 b $MAJOR $MINOR
          mkdir /mnt
          mount /dev/vda1 /mnt

          # The initrd expects these directories to exist.
          mount --bind /proc /mnt/proc
          mount --bind /dev /mnt/dev
          mount --bind /sys /mnt/sys

          # Avoid "groups does not exist" warnings
          mkdir -p /etc/nix
          echo 'build-users-group = ' > /etc/nix/nix.conf
          mkdir -p /mnt/etc/nix
          echo 'build-users-group = ' > /mnt/etc/nix/nix.conf

          sourceStore='${pkgs.nix}/bin/nix-store'
          targetStore='chroot /mnt ${cfg.nix.package.out}/bin/nix-store'

          echo "filling Nix store..."
          set -f

          # Copy missing paths in the closure to the target nix store.
          storePaths=$(perl ${pkgs.pathsFromGraph} /tmp/xchg/closure)
          missing=$(NIX_DB_DIR=/mnt/nix/var/nix/db $sourceStore --check-validity --print-invalid $storePaths)
          for path in $missing; do
              ${pkgs.rsync}/bin/rsync -a $path /mnt/nix/store/
          done

          # Register the paths in the Nix database.
          $targetStore --register-validity < /tmp/xchg/closure

          # TODO: Replace with the following
          # when https://github.com/NixOS/nix/issues/1134 is fixed
          #printRegistration=1 perl ${pkgs.pathsFromGraph} /tmp/xchg/closure | $sourceStore --load-db
          #$sourceStore --export $missing | $targetStore --import


          # Create the system profile to allow nixos-rebuild to work.
          chroot /mnt ${cfg.nix.package.out}/bin/nix-env \
              -p /nix/var/nix/profiles/system --set ${cfg.system.build.toplevel}

          # Generate the GRUB menu.
          ln -s vda /dev/sda
          chroot /mnt ${cfg.system.build.toplevel}/bin/switch-to-configuration boot

          umount /mnt/proc /mnt/dev /mnt/sys
          umount /mnt
        ''
    );
}
