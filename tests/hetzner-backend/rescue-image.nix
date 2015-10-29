{ pkgs }:

let
  rescueDiskImageFun = pkgs.vmTools.diskImageFuns.debian8x86_64;
  rescueDebDistro = pkgs.vmTools.debDistros.debian8x86_64;
  rescueDebCodename = "jessie";

  fetchBackport = { name, version, arch ? "all", archive ? name, sha256 }: let
    filename = "${name}_${version}_${arch}.deb";
    archiveLetter = builtins.substring 0 1 archive;
  in (pkgs.fetchurl {
    name = builtins.replaceStrings ["~"] ["-"] filename;
    url = "mirror://debian/pool/main/${archiveLetter}/${archive}/${filename}";
    inherit sha256;
  }) // { packageName = name; };

  newKernel = [
    (fetchBackport {
      name = "linux-image-4.2.0-0.bpo.1-amd64";
      version = "4.2.3-2~bpo8+1";
      arch = "amd64";
      archive = "linux";
      sha256 = "0jlwmycdc4xsn2vapbidyp47zrpihj6qgk7p0rjw6fxl86yas56s";
    })
    (fetchBackport {
      name = "linux-image-amd64";
      version = "4.2+68~bpo8+2";
      arch = "amd64";
      archive = "linux-latest";
      sha256 = "0bhk3wik3bvkha61cqwgx7pg7bqs2q82kxivacqqja2nqzjww2d7";
    })
    (fetchBackport {
      name = "linux-base";
      version = "4.0~bpo8+1";
      arch = "all";
      archive = "linux-base";
      sha256 = "0nacjll097vhphgvgpzgy3avgxrjrjm0nf4xlzc2hjgrv4gy3hhr";
    })
    # Needed because AUFS has been replaced by overlayfs in the new kernel.
    (fetchBackport {
      name = "live-tools";
      version = "5.0~a2-1";
      sha256 = "0vivl2qkbjmibjgh9diyjbdl9izsn26aclgh4d04kc6jri606693";
    })
    (fetchBackport {
      name = "live-boot";
      version = "5.0~a5-1";
      sha256 = "1402k0xygrljk2ng2lbb7jhg4a23sqmdgn0bhms0a34f5w12rnyp";
    })
    (fetchBackport {
      name = "live-boot-initramfs-tools";
      version = "5.0~a5-1";
      archive = "live-boot";
      sha256 = "1ylny8hvwliqnva9z5c82qqmxm3skc8fh50lz5fva4mfkzk9zzbh";
    })
    (fetchBackport {
      name = "live-config";
      version = "5.0~a5-1";
      sha256 = "1146hwml89cp7f18xwm4q9fj8yy9hlki93h179v41pzha1b9jskz";
    })
    (fetchBackport {
      name = "live-config-systemd";
      version = "5.0~a5-1";
      archive = "live-config";
      sha256 = "1q2586vxavhz3dc98m1pccim1d8qpcfyskrzmszgi8bnqqn22x2c";
    })
  ];

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
    "apt" "hostname" "tasksel" "makedev" "locales" "kbd" "console-setup"
    "console-common" "eject" "file" "user-setup" "sudo" "squashfs-tools"
    "syslinux-common" "syslinux" "isolinux" "genisoimage" "live-boot" "zsync"
    "librsvg2-bin" "dctrl-tools" "xorriso" "live-config" "live-config-systemd"
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
    extraPackages = [ backdoorDeb ] ++ newKernel;
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
    echo backdoor ${toString (map (p: p.packageName) newKernel)} \
      > config/package-lists/custom.list.chroot

    cp -rT "${live-build}/share/live/build/bootloaders" \
      config/bootloaders
    sed -i -e 's/timeout 0/timeout 1/' \
      config/bootloaders/isolinux/isolinux.cfg

    if ! lb build; then
      cat /build_fake_rescue/chroot/debootstrap/debootstrap.log >&2
      exit 1
    fi

    kill -TERM $(< repo.pid)
    chmod 0644 live-image-*.iso
    mv live-image-*.iso "$out/rescue.iso"
  '';
})
