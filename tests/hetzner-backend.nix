{ system, nixops }:

with import <nixos/lib/testing.nix> { inherit system; };
with import <nixos/lib/qemu-flags.nix>;
with pkgs.lib;

let
  rescuePasswd = "abcd1234";

  network = pkgs.writeText "network.nix" ''
    {
      network.description = "Hetzner test";

      target1 = {
        deployment.targetEnv = "hetzner";
        deployment.hetzner.mainIPv4 = "192.168.1.2";
        deployment.hetzner.partitions = '''
          clearpart --all --initlabel --drives=vda,vdb

          part swap1 --recommended --label=swap1 --fstype=swap --ondisk=vda
          part swap1 --recommended --label=swap2 --fstype=swap --ondisk=vdb

          part raid.1 --grow --ondisk=vda
          part raid.2 --grow --ondisk=vdb

          raid / --level=1 --device=md0 --fstype=ext4 \
                 --label=root raid.1 raid.2
        ''';
      };

      target2 = {
        deployment.targetEnv = "hetzner";
        deployment.hetzner.mainIPv4 = "192.168.1.3";
        deployment.hetzner.partitions = '''
          clearpart --all --initlabel --drives=vda,vdb

          part swap1 --recommended --label=swap1 --fstype=swap --ondisk=vda
          part swap2 --recommended --label=swap2 --fstype=swap --ondisk=vdb

          part btrfs.1 --grow --ondisk=vda
          part btrfs.2 --grow --ondisk=vdb

          btrfs / --data=1 --metadata=1 \
                  --label=root btrfs.1 btrfs.2
        ''';
      };
    }
  '';

  # Packages needed by live-build (Debian Squeeze)
  rescuePackages = pkgs.vmTools.debDistros.debian60x86_64.packages ++ [
    "apt" "hostname" "tasksel" "makedev" "locales" "kbd" "linux-image-2.6-amd64"
    "live-initramfs" "console-setup" "console-common" "eject" "file"
    "user-setup" "sudo" "squashfs-tools" "syslinux" "genisoimage" "live-boot"
    "zsync" "librsvg2-bin" "net-tools" "dctrl-tools"
  ];

  # Packages to be explicitely installed into the live system.
  additionalRescuePackages = [
    "openssh-server" "e2fsprogs" "mdadm" "btrfs-tools" "dmsetup" "iproute"
  ];

  # Debian packages for the rescue live system (Squeeze).
  rescueDebs = let
    expr = pkgs.vmTools.debClosureGenerator {
      packages = rescuePackages ++ additionalRescuePackages;
      inherit (pkgs.vmTools.debDistros.debian60x86_64) name urlPrefix;
      packagesLists = [pkgs.vmTools.debDistros.debian60x86_64.packagesList];
    };
  in import expr {
    inherit (pkgs) fetchurl;
  };

  # This more or less resembles an image of the Hetzner's rescue system.
  rescueISO = pkgs.vmTools.runInLinuxImage (pkgs.stdenv.mkDerivation {
    name = "hetzner-fake-rescue-image";
    diskImage = pkgs.vmTools.diskImageFuns.debian70x86_64 {
      extraPackages = [ "live-build" "cdebootstrap" "reprepro" ];
    };
    memSize = 768;

    inherit rescueDebs;
    inherit additionalRescuePackages;

    bootOptions = [
      "boot=live"
      "config"
      "console=ttyS0,9600"
      "hostname=rescue"
      "timezone=Europe/Berlin"
      # We're going to eject silently on our own, see chroot hooks below.
      "noeject"
      "quickreboot"
    ];

    buildCommand = ''
      # Operate on the temporary root filesystem instead of the tmpfs.
      mkdir -p /build_fake_rescue
      cd /build_fake_rescue

      mkdir -p debcache/{conf,dists,incoming,indices,logs,pool,project,tmp}
      cat > debcache/conf/distributions <<RELEASE
      Origin: Debian
      Label: Debian
      Codename: squeeze
      Architectures: amd64
      Components: main
      Contents:
      Description: Debian package cache
      RELEASE

      # Create APT repository
      echo -n "Creating APT repository..." >&2
      for debfile in $rescueDebs; do
        REPREPRO_BASE_DIR=debcache reprepro includedeb squeeze "$debfile" \
          > /dev/null
      done
      echo " done." >&2

      # Serve APT repository
      ${pkgs.thttpd}/sbin/thttpd -d debcache \
                                 -l /dev/null \
                                 -i "$(pwd)/thttpd.pid"

      lb config --memtest none \
                --binary-images iso \
                --distribution squeeze \
                --bootstrap cdebootstrap \
                --debconf-frontend noninteractive \
                --bootappend-live "$bootOptions" \
                --mirror-bootstrap http://127.0.0.1 \
                --debian-installer false

      sed -i -e 's/^LB_APT_SECURE=.*/LB_APT_SECURE=false/' config/common

      cat > config/hooks/1000-root_password.chroot <<ROOTPW
      echo "root:${rescuePasswd}" | chpasswd
      ROOTPW

      cat > config/hooks/1001-backdoor.chroot <<BACKDOOR
      cat > /usr/local/bin/backdoor <<BACKDOOR_SCRIPT
      #!/bin/sh
      export USER=root
      export HOME=/root
      . /etc/profile
      cd /tmp
      exec < /dev/hvc0 > /dev/hvc0
      while ! exec 2> /dev/ttyS0; do sleep 0.1; done
      echo "connecting to host..." >&2
      stty -F /dev/hvc0 raw -echo
      echo
      PS1= exec /bin/sh
      BACKDOOR_SCRIPT
      chmod +x /usr/local/bin/backdoor

      echo 'T0:23:respawn:/usr/local/bin/backdoor' >> /etc/inittab
      BACKDOOR

      # Patch reboot command to always eject the ISO silently.
      cat > config/hooks/1002-patch_reboot.chroot <<PATCHREBOOT
      sed -i -e '/^do_stop/a eject -m /dev/scd0' /etc/init.d/reboot
      PATCHREBOOT

      echo $additionalRescuePackages \
        > config/package-lists/additional.list.chroot

      cat > config/hooks/1000-isolinux_timeout.binary <<ISOLINUX
      sed -i -e 's/timeout 0/timeout 1/' binary/isolinux/isolinux.cfg
      ISOLINUX

      # Ugly workaround for http://bugs.debian.org/643659
      lb build || lb build

      kill -TERM $(< thttpd.pid)
      chmod 0644 binary.iso
      mv binary.iso "$out/rescue.iso"
    '';
  });

  env = "NIX_PATH=nixos=${<nixos>}:nixpkgs=${<nixpkgs>}"
      + " HETZNER_ROBOT_USER=none HETZNER_ROBOT_PASS=none";

  targetQemuFlags = targetId: let
    mkDrive = file: "-drive " + (concatStringsSep "," [
      "file='.$imgdir.'/${file}"
      "if=virtio"
      "cache=writeback"
      "werror=report"
    ]);
    flags = [
      "-m 512"
      "-cpu kvm64"
      (mkDrive "harddisk${toString targetId}_2")
      (mkDrive "cacheimg${toString targetId}")
    ] ++ (qemuNICFlags 1 1 (builtins.add targetId 1));
  in concatStringsSep " " flags;

in makeTest ({ pkgs, ... }:
{
  nodes = {
    coordinator = {
      environment.systemPackages = [ nixops ];
    };
  };

  testScript = ''
    $coordinator->start;

    createDisk("harddisk1_1", 4 * 1024);
    createDisk("harddisk1_2", 4 * 1024);

    createDisk("harddisk2_1", 4 * 1024);
    createDisk("harddisk2_2", 4 * 1024);

    # Temporary Nix stores for the partitioner.
    createDisk("cacheimg1", 1024);
    createDisk("cacheimg2", 1024);

    my $imgdir = `pwd`;
    chomp($imgdir);

    my $target1 = createMachine({
      name => "target1",
      hda => "harddisk1_1",
      cdrom => "${rescueISO}/rescue.iso",
      qemuFlags => '${targetQemuFlags 1}',
      allowReboot => 1,
    });

    $target1->start;
    $target1->succeed("echo 2 > /proc/sys/vm/panic_on_oom");
    $target1->succeed("mkfs.ext4 /dev/vdc");
    $target1->succeed("mkdir -p /nix && mount /dev/vdc /nix");
    $target1->succeed("ifconfig eth1 192.168.1.2");
    $target1->succeed("modprobe dm-mod");

    my $target2 = createMachine({
      name => "target2",
      hda => "harddisk2_1",
      cdrom => "${rescueISO}/rescue.iso",
      qemuFlags => '${targetQemuFlags 2}',
      allowReboot => 1,
    });

    $target2->start;
    $target2->succeed("echo 2 > /proc/sys/vm/panic_on_oom");
    $target2->succeed("mkfs.ext4 /dev/vdc");
    $target2->succeed("mkdir -p /nix && mount /dev/vdc /nix");
    $target2->succeed("ifconfig eth1 192.168.1.3");
    $target2->succeed("modprobe dm-mod");

    $coordinator->waitForJob("network-interfaces.target");
    $coordinator->succeed("ping -c1 192.168.1.2");
    $coordinator->succeed("ping -c1 192.168.1.3");

    $coordinator->succeed("cp ${network} network.nix");
    $coordinator->succeed("nixops create network.nix");

    # Do deployment on one target at a time to avoid running out of memory.
    $coordinator->succeed("${env} nixops info >&2");
    $coordinator->succeed("${env} nixops deploy --include=target1");
    $coordinator->succeed("${env} nixops info >&2");
    $coordinator->succeed("${env} nixops deploy --include=target2");
    $coordinator->succeed("${env} nixops info >&2");
  '';
})
