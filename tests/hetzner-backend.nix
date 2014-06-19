{ system, nixops }:

with import <nixpkgs/nixos/lib/testing.nix> { inherit system; };
with import <nixpkgs/nixos/lib/qemu-flags.nix>;
with pkgs.lib;

let
  rescuePasswd = "abcd1234";

  network = pkgs.writeText "network.nix" ''
    let
      withCommonOptions = otherOpts: { config, ... }: {
        require = [
          <nixpkgs/nixos/modules/profiles/qemu-guest.nix>
          <nixpkgs/nixos/modules/testing/test-instrumentation.nix>
        ];

        networking.useDHCP = false;

        # We don't want to include everything from qemu-vm.nix,
        # so we're going to just pick the options we need (and
        # qemu-guest.nix above in the require attribute).
        services.ntp.enable = false;
        system.requiredKernelConfig = with config.lib.kernelConfig; [
          (isEnabled "VIRTIO_BLK")
          (isEnabled "VIRTIO_PCI")
          (isEnabled "VIRTIO_NET")
          (isEnabled "EXT4_FS")
          (isEnabled "BTRFS_FS")
          (isYes "BLK_DEV")
          (isYes "PCI")
          (isYes "EXPERIMENTAL")
          (isYes "NETDEVICES")
          (isYes "NET_CORE")
          (isYes "INET")
          (isYes "NETWORK_FILESYSTEMS")
        ];
      } // otherOpts;
    in {
      network.description = "Hetzner test";

      target1 = withCommonOptions {
        deployment.targetEnv = "hetzner";
        deployment.hetzner.mainIPv4 = "192.168.1.2";
        deployment.hetzner.partitions = '''
          clearpart --all --initlabel --drives=vda,vdb

          part swap1 --recommended --label=swap1 --fstype=swap --ondisk=vda
          part swap2 --recommended --label=swap2 --fstype=swap --ondisk=vdb

          part raid.1 --grow --ondisk=vda
          part raid.2 --grow --ondisk=vdb

          raid / --level=1 --device=md0 --fstype=ext4 \
                 --label=root raid.1 raid.2
        ''';
      };

      target2 = withCommonOptions {
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

  # Packages needed by live-build (Debian Wheezy)
  rescuePackages = pkgs.vmTools.debDistros.debian70x86_64.packages ++ [
    "apt" "hostname" "tasksel" "makedev" "locales" "kbd" "linux-image-2.6-amd64"
    "console-setup" "console-common" "eject" "file" "user-setup" "sudo"
    "squashfs-tools" "syslinux" "genisoimage" "live-boot" "zsync" "librsvg2-bin"
    "dctrl-tools" "xorriso" "live-config" "live-config-sysvinit"
  ];

  # Packages to be explicitly installed into the live system.
  additionalRescuePackages = [
    "openssh-server" "e2fsprogs" "mdadm" "btrfs-tools" "dmsetup" "iproute"
    "net-tools"
  ];

  # Debian packages for the rescue live system (Wheezy).
  rescueDebs = let
    expr = pkgs.vmTools.debClosureGenerator {
      packages = rescuePackages ++ additionalRescuePackages;
      inherit (pkgs.vmTools.debDistros.debian70x86_64) name urlPrefix;
      packagesLists = [pkgs.vmTools.debDistros.debian70x86_64.packagesList];
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
      Codename: wheezy
      Architectures: amd64
      Components: main
      Contents:
      Description: Debian package cache
      RELEASE

      # Create APT repository
      echo -n "Creating APT repository..." >&2
      for debfile in $rescueDebs; do
        REPREPRO_BASE_DIR=debcache reprepro includedeb wheezy "$debfile" \
          > /dev/null
      done
      echo " done." >&2

      # Serve APT repository
      ${pkgs.thttpd}/sbin/thttpd -d debcache \
                                 -l /dev/null \
                                 -i "$(pwd)/thttpd.pid"

      lb config --memtest none \
                --apt-secure false \
                --binary-images iso \
                --distribution wheezy \
                --bootstrap cdebootstrap \
                --debconf-frontend noninteractive \
                --bootappend-live "$bootOptions" \
                --mirror-bootstrap http://127.0.0.1 \
                --debian-installer false

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

      # Ensure that GPG is avoided in postinst of cdebootstrap-helper-apt
      mkdir -p chroot/bin
      cat > chroot/bin/apt-get <<NOGPG
      #!/bin/sh
      # Setting APT::Get::AllowUnauthenticated in apt.conf doesn't seem to have
      # any effect here, so we simply wrap apt-get and prepend the flag. Also,
      # on "apt-get update" let's always return with exit status 0, because we
      # don't actually care whether it fails as long as the packages can be
      # installed.
      if ! /usr/bin/apt-get --allow-unauthenticated "\$@"; then
        case "\$*" in
          *update*) exit 0;;
          *) exit \$?;;
        esac
      fi
      NOGPG
      chmod +x chroot/bin/apt-get

      echo $additionalRescuePackages \
        > config/package-lists/additional.list.chroot

      cat > config/hooks/1000-isolinux_timeout.binary <<ISOLINUX
      sed -i -e 's/timeout 0/timeout 1/' binary/isolinux/isolinux.cfg
      ISOLINUX

      # Remove the APT workaround concerning GPG
      cat > config/hooks/1001-remove_apt_hack.binary <<REMOVEAPT
      rm -f chroot/bin/apt-get
      REMOVEAPT

      # Ugly workaround for http://bugs.debian.org/643659
      lb build || lb build

      kill -TERM $(< thttpd.pid)
      chmod 0644 binary.iso
      mv binary.iso "$out/rescue.iso"
    '';
  });

  env = "NIX_PATH=nixos=${<nixpkgs>}/nixos:nixpkgs=${<nixpkgs>}"
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
      "-boot order=c,once=d"
      (mkDrive "harddisk${toString targetId}_2")
      (mkDrive "cacheimg${toString targetId}")
    ] ++ (qemuNICFlags 1 1 (builtins.add targetId 1));
  in concatStringsSep " " flags;

in makeTest {
  nodes.coordinator = {
    environment.systemPackages = let
      testNixops = overrideDerivation nixops (o: {
        postPatch = ''
          sed -i -e 's/^TEST_MODE.*/TEST_MODE = True/' \
            nixops/backends/hetzner.py
        '';
      });
      # XXX: Workaround to prepopulate the Nix store of the coordinator.
      collection = pkgs.myEnvFun {
        name = "prepopulate";
        buildInputs = [
          # This is to have the bootstrap installer prebuilt inside the Nix
          # store of the target machine.
          (import ../nix/hetzner-bootstrap.nix)
          # ... and this is for other requirements for a basic deployment.
          pkgs.stdenv pkgs.busybox pkgs.module_init_tools pkgs.grub2
          pkgs.xfsprogs pkgs.btrfsProgs pkgs.docbook_xsl_ns pkgs.libxslt
          pkgs.docbook5 pkgs.ntp
          # Firmware used in <nixpkgs/nixos/modules/installer/scan/not-detected.nix>
          pkgs.firmwareLinuxNonfree
        ];
      };
    in [ testNixops collection ];
    virtualisation.writableStore = true;
    virtualisation.writableStoreUseTmpfs = false;
    virtualisation.memorySize = 2048;
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

    subtest "start virtual rescue for target 1", sub {
      $target1->start;
      $target1->succeed("echo 2 > /proc/sys/vm/panic_on_oom");
      $target1->succeed("mkfs.ext4 /dev/vdc");
      $target1->succeed("mkdir -p /nix && mount /dev/vdc /nix");
      $target1->succeed("ifconfig eth1 192.168.1.2");
      $target1->succeed("modprobe dm-mod");
    };

    my $target2 = createMachine({
      name => "target2",
      hda => "harddisk2_1",
      cdrom => "${rescueISO}/rescue.iso",
      qemuFlags => '${targetQemuFlags 2}',
      allowReboot => 1,
    });

    subtest "start virtual rescue for target 2", sub {
      $target2->start;
      $target2->succeed("echo 2 > /proc/sys/vm/panic_on_oom");
      $target2->succeed("mkfs.ext4 /dev/vdc");
      $target2->succeed("mkdir -p /nix && mount /dev/vdc /nix");
      $target2->succeed("ifconfig eth1 192.168.1.3");
      $target2->succeed("modprobe dm-mod");
      # XXX: Work around failure on mkfs.btrfs
      $target2->succeed("mkdir -p /live/medium/live/filesystem.squashfs");
    };

    $coordinator->waitForJob("network-interfaces.target");

    subtest "targets reachable", sub {
      $coordinator->succeed("ping -c1 192.168.1.2");
      $coordinator->succeed("ping -c1 192.168.1.3");
    };

    subtest "create deployment", sub {
      $coordinator->succeed("cp ${network} network.nix");
      $coordinator->succeed("nixops create network.nix");
    };

    # Do deployment on one target at a time to avoid running out of memory.
    subtest "deploy target 1", sub {
      $coordinator->succeed("${env} nixops info >&2");
      $coordinator->succeed("${env} nixops deploy --include=target1");
    };

    subtest "deploy target 2", sub {
      $coordinator->succeed("${env} nixops info >&2");
      $coordinator->succeed("${env} nixops deploy --include=target2");
    };


    # Bring everything up-to-date.
    subtest "deploy all targets", sub {
      $coordinator->succeed("${env} nixops info >&2");
      $coordinator->succeed("${env} nixops deploy");
      $coordinator->succeed("${env} nixops info >&2");
    };

    subtest "filesystems", sub {
      # Check if we have the right file systems by using NixOps...
      $coordinator->succeed("${env} nixops ssh target1 -- " .
                            "mount | grep -F 'on / type ext4'");
      $coordinator->succeed("${env} nixops ssh target2 -- " .
                            "mount | grep -F 'on / type btrfs'");

      # ... and directly without using NixOps.
      $target1->succeed("mount | grep -F 'on / type ext4'");
      $target2->succeed("mount | grep -F 'on / type btrfs'");
    };
  '';
}
