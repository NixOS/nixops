{ pkgs }:

let
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
in pkgs.vmTools.runInLinuxImage (pkgs.stdenv.mkDerivation {
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
})
