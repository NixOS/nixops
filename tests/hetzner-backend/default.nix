{ system, nixops }:

with import <nixpkgs/nixos/lib/testing.nix> { inherit system; };
with pkgs.lib;

let
  flagsExpr = import <nixpkgs/nixos/lib/qemu-flags.nix>;
  qemuFlags = if isAttrs flagsExpr then flagsExpr
              else flagsExpr { inherit pkgs; };
  inherit (qemuFlags) qemuNICFlags;

  rescueISO = import ./rescue-image.nix { inherit pkgs; };
  rescuePasswd = "abcd1234";

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

  env = "NIX_PATH=nixpkgs=${<nixpkgs>}"
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
  name = "hetzner-backend";

  nodes.coordinator = {
    networking.firewall.enable = false;
    environment.systemPackages = singleton (overrideDerivation nixops (o: {
      postPatch = ''
        sed -i -e 's/^TEST_MODE.*/TEST_MODE = True/' \
          nixops/backends/hetzner.py
      '';
    }));

    # This is needed to make sure the coordinator can build the
    # deployment without network availability.
    system.extraDependencies = [
      # This is to have the bootstrap installer prebuilt inside the Nix
      # store of the target machine.
      (import ../../nix/hetzner-bootstrap.nix)
      # ... and this is for other requirements for a basic deployment.
      pkgs.stdenv pkgs.busybox pkgs.module_init_tools pkgs.grub2
      pkgs.xfsprogs pkgs.btrfsProgs pkgs.docbook_xsl_ns
      pkgs.docbook5 pkgs.ntp pkgs.perlPackages.ArchiveCpio
      (pkgs.libxslt.dev or pkgs.libxslt)
      (pkgs.libxml2.dev or pkgs.libxml2)
      # Firmware used in <nixpkgs/nixos/modules/installer/scan/not-detected.nix>
      pkgs.firmwareLinuxNonfree
    ];

    virtualisation.writableStore = true;
    virtualisation.writableStoreUseTmpfs = false;
    virtualisation.memorySize = 2048;
  };

  testScript = ''
    my %ips;

    sub startRescue ($) {
      my $node = shift;
      my $ip = $ips{$node->name};
      $node->nest("starting up rescue system for {$node->name}", sub {
        if ($node->isUp) {
          $node->sendMonitorCommand("boot_set order=c,once=d");
          $node->shutdown;
        }

        $node->start;
        $node->succeed("echo acpi_pm > /sys/devices/system/clocksource/" .
                       "clocksource0/current_clocksource");
        $node->succeed("echo 2 > /proc/sys/vm/panic_on_oom");
        $node->succeed("mkfs.ext4 -F /dev/vdc");
        $node->succeed("mkdir -p /nix && mount /dev/vdc /nix");
        $node->succeed("ifconfig eth1 $ip");
        $node->succeed("modprobe dm-mod");
        $node->succeed("echo 'root:${rescuePasswd}' | chpasswd");
        my $re = 's/^(PermitRootLogin|PasswordAuthentication) .*/\\1 yes/';
        $node->succeed("sed -i -re '$re' /etc/ssh/sshd_config");
        $node->succeed("systemctl restart ssh");
      });
      return $node;
    };

    sub setupAndStartRescue {
      my ($name, $hda, $qemuFlags, $ip) = @_;
      $ips{$name} = $ip;
      my $node = createMachine({
        name => $name,
        hda => $hda,
        cdrom => "${rescueISO}/rescue.iso",
        qemuFlags => $qemuFlags,
        allowReboot => 1,
      });
      return startRescue $node;
    };

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

    my $target1 = setupAndStartRescue(
      "target1", "harddisk1_1", '${targetQemuFlags 1}', "192.168.1.2"
    );

    my $target2 = setupAndStartRescue(
      "target2", "harddisk2_1", '${targetQemuFlags 2}', "192.168.1.3"
    );

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

    subtest "can ssh to rescue system", sub {
      startRescue $target1;
      $coordinator->succeed("${env} nixops reboot --hard --rescue " .
                            "--include=target1");
      $coordinator->succeed("${env} nixops ssh target1 -- " .
                            "cat /etc/debian_version >&2");
    };

    # Bring everything up-to-date.
    subtest "deploy all targets", sub {
      $coordinator->succeed("${env} nixops info >&2");
      $coordinator->succeed("${env} nixops deploy --allow-reboot");
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
