{ system, nixops }:

with import <nixos/lib/testing.nix> { inherit system; };
with import <nixos/lib/qemu-flags.nix>;
with pkgs.lib;

let
  rescuePasswd = "abcd1234";

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

in makeTest ({ pkgs, ... }:
{
  nodes = {
    coordinator = {
      environment.systemPackages = [ nixops ];
    };
  };

  testScript = ''
    $coordinator->start;

    createDisk("harddisk1", 4 * 1024);
    createDisk("harddisk2", 4 * 1024);

    my $target1 = createMachine({
      name => "target1",
      hda => "harddisk1",
      cdrom => "${rescueISO}/rescue.iso",
      qemuFlags => '${toString (qemuNICFlags 1 1 2)} -cpu kvm64',
    });

    $target1->start;
    $target1->succeed("/sbin/ifconfig eth1 192.168.1.2");

    my $target2 = createMachine({
      name => "target2",
      hda => "harddisk2",
      cdrom => "${rescueISO}/rescue.iso",
      qemuFlags => '${toString (qemuNICFlags 1 1 3)} -cpu kvm64',
    });

    $target2->start;
    $target2->succeed("/sbin/ifconfig eth1 192.168.1.3");

    $coordinator->waitForJob("network-interfaces.target");
    $coordinator->succeed("ping -c1 192.168.1.2");
    $coordinator->succeed("ping -c1 192.168.1.3");
  '';
})
