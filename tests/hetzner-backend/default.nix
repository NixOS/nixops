{ system, nixops }:

with import <nixpkgs/nixos/lib/testing.nix> { inherit system; };
with import <nixpkgs/nixos/lib/qemu-flags.nix>;
with pkgs.lib;

let
  rescuePasswd = "abcd1234";

  rescueDiskImageFun = pkgs.vmTools.diskImageFuns.debian8x86_64;
  rescueDebDistro = pkgs.vmTools.debDistros.debian8x86_64;
  rescueDebCodename = "jessie";

  live-build = pkgs.stdenv.mkDerivation rec {
    name = "live-build-${version}";
    version = "5.0_a11";

    src = pkgs.fetchgit {
      url = "git://live.debian.net/git/live-build.git";
      rev = "refs/tags/debian/${version}-1";
      sha256 = "0c3kqqsw4pxrnmjqphs8ifcm78yly6zdvnylg9s6njga7mb951g9";
    };

    dontPatchShebangs = true;

    postPatch = ''
      find -type f -exec sed -i \
        -e 's,/usr/lib/live,'"$out"'/lib/live,g' \
        -e 's,/usr/share/live,'"$out"'/share/live,g' \
        {} +
      sed -i \
        -e 's,/usr/bin,'"$out"'/bin,' \
        -e 's,/usr/share,'"$out"'/share,' \
        Makefile
    '';
  };

  network = pkgs.writeText "network.nix" ''
    let
      withCommonOptions = otherOpts: { config, ... }: {
        require = [
          <nixpkgs/nixos/modules/profiles/qemu-guest.nix>
          <nixpkgs/nixos/modules/testing/test-instrumentation.nix>
        ];

        networking.useDHCP = false;
        networking.firewall.enable = false;

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

  # Packages needed by live-build
  rescuePackages = [
    "apt" "hostname" "tasksel" "makedev" "locales" "kbd" "linux-image-amd64"
    "console-setup" "console-common" "eject" "file" "user-setup" "sudo"
    "squashfs-tools" "syslinux-common" "syslinux" "isolinux" "genisoimage"
    "live-boot" "zsync" "librsvg2-bin" "dctrl-tools" "xorriso" "live-config"
    "live-config-systemd"
  ];

  # Packages to be explicitly installed into the live system.
  additionalRescuePackages = [
    "openssh-server" "e2fsprogs" "mdadm" "btrfs-tools" "dmsetup" "iproute"
    "net-tools"
  ];

  backdoorDeb = import ./backdoor.nix {
    inherit pkgs;
    diskImageFun = rescueDiskImageFun;
  };

  aptRepository = import ./repository.nix {
    inherit pkgs;
    diskImageFun = rescueDiskImageFun;
    debianDistro = rescueDebDistro;
    debianCodename = rescueDebCodename;
    debianPackages = rescuePackages ++ additionalRescuePackages;
    extraPackages = [ backdoorDeb ];
  };

  # This more or less resembles an image of the Hetzner's rescue system.
  rescueISO = pkgs.vmTools.runInLinuxImage (pkgs.stdenv.mkDerivation {
    name = "hetzner-fake-rescue-image";
    diskImage = rescueDiskImageFun {
      extraPackages = [ "debootstrap" "apt" ];
    };
    memSize = 768;

    inherit additionalRescuePackages;

    bootOptions = [
      "boot=live"
      "config"
      "console=ttyS0"
      "hostname=rescue"
      "timezone=Europe/Berlin"
      "noeject"
      "quickreboot"
    ];

    buildCommand = ''
      # Operate on the temporary root filesystem instead of the tmpfs.
      mkdir -p /build_fake_rescue
      cd /build_fake_rescue

      PATH="${pkgs.gnupg}/bin:${live-build}/bin:${pkgs.cpio}/bin:$PATH"

      ${aptRepository.serve}

      lb config --memtest none \
                --apt-secure false \
                --apt-source-archives false \
                --binary-images iso \
                --distribution "${rescueDebCodename}" \
                --debconf-frontend noninteractive \
                --debootstrap-options "--include=snakeoil-archive-keyring" \
                --bootappend-live "$bootOptions" \
                --mirror-bootstrap http://127.0.0.1 \
                --mirror-binary http://127.0.0.1 \
                --debian-installer false \
                --security false \
                --updates false \
                --backports false \
                --source false \
                --firmware-binary false \
                --firmware-chroot false

      mkdir -p config/includes.chroot/etc/systemd/journald.conf.d
      echo rescue > config/includes.chroot/etc/hostname
      cat > config/includes.chroot/etc/systemd/journald.conf.d/log.conf <<EOF
      [Journal]
      ForwardToConsole=yes
      MaxLevelConsole=debug
      EOF

      echo $additionalRescuePackages \
        > config/package-lists/additional.list.chroot
      echo backdoor \
        > config/package-lists/custom.list.chroot

      cp -rT "${live-build}/share/live/build/bootloaders" \
        config/bootloaders
      sed -i -e 's/timeout 0/timeout 1/' \
        config/bootloaders/isolinux/isolinux.cfg

      lb build

      kill -TERM $(< repo.pid)
      chmod 0644 live-image-*.iso
      mv live-image-*.iso "$out/rescue.iso"
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
    networking.firewall.enable = false;
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
          (import ../../nix/hetzner-bootstrap.nix)
          # ... and this is for other requirements for a basic deployment.
          pkgs.stdenv pkgs.busybox pkgs.module_init_tools pkgs.grub2
          pkgs.xfsprogs pkgs.btrfsProgs pkgs.docbook_xsl_ns pkgs.libxslt
          pkgs.docbook5 pkgs.ntp pkgs.perlPackages.ArchiveCpio
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
      $target1->succeed("echo 'root:${rescuePasswd}' | chpasswd");
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
      $target2->succeed("echo 'root:${rescuePasswd}' | chpasswd");
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
