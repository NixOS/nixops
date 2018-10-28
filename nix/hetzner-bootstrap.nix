with import <nixpkgs> { system = "x86_64-linux"; };

let
  pkgsNative = import <nixpkgs> {};

  nixpart = python2Packages.nixpart0.override {
    useNixUdev = false;
  };

  generateConfig = (import <nixpkgs/nixos> {
    configuration = {};
  }).config.system.build.nixos-generate-config;

  base = stdenv.mkDerivation {
    name = "hetzner-nixops-base";

    buildCommand = ''
      mkdir -p "$out/bin"
      ln -s "${nix}"/bin/* "$out/bin/"
      ln -s "${stdenv.shell}" "$out/bin/sh"
      ln -s "${pkgsNative.cacert}" "$out/etc-certs"
    '';
  };
in stdenv.mkDerivation {
  name = "hetzner-nixops-installer";

  exportReferencesGraph = [
    "refs-base" base
    "refs-nixpart" nixpart
    "refs-genconf" generateConfig
  ];

  buildCommand = ''
    mkdir -p "usr/bin" "$out/bin"
    installer="$out/bin/hetzner-bootstrap"
    syspath="/nix/var/nix/profiles/system/sw";

    mkChrootWrapper() {
      local name="$1"
      local dest="$2"
      local fullpath="$3"

      local wrapper="usr/bin/$name"
      ( echo "#!/bin/sh"
        echo "export SSL_CERT_FILE=${pkgsNative.cacert}/etc/ssl/certs/ca-bundle.crt"
        echo "export PATH=\"$syspath/bin\''${PATH:+:}\$PATH\""
        if [ -n "$fullpath" ]; then
          echo "if chroot /mnt \"$syspath/bin/true\" > /dev/null 2>&1; then"
          echo "  exec chroot /mnt \"$syspath/bin/$dest\" \$@"
          echo "else"
          echo "  exec chroot /mnt \"$fullpath\" \$@"
          echo "fi"
        else
          echo "exec chroot /mnt \"$syspath/bin\"/$dest"
        fi
      ) > "$wrapper"
      chmod +x "$wrapper"
    }

    # Create the chroot wrappers for Nix
    for path in "${nix}"/bin/*; do
      base="$(basename "$path")"
      mkChrootWrapper "$base" "$base" "$path"
    done

    mkChrootWrapper nixos-enter "su -"

    # Only a symlink that is going to be put into the Tar file.
    ln -ns "${nixpart}/bin/nixpart" usr/bin/nixpart
    ln -ns "${generateConfig}/bin/nixos-generate-config" \
           usr/bin/nixos-generate-config

    base_storepaths="$("${perl}/bin/perl" "${pathsFromGraph}" refs-base)"
    base_registration="$(printRegistration=1 \
      "${perl}/bin/perl" "${pathsFromGraph}" refs-base)"

    ( # Don't use stdenv.shell here, we're NOT on NixOS!
      echo "#!/bin/sh"
      # Do not quote because we want to inline the paths!
      echo 'mkdir -m 1777 -p "/mnt/nix/store"'
      echo "cp -a" $base_storepaths "/mnt/nix/store/"
      echo "chroot /mnt \"${base}/bin/nix-store\" --load-db <<'REGINFO'"
      echo "$base_registration"
      echo "REGINFO"
      echo 'ln -sn "${stdenv.shell}" /mnt/bin/sh'
    ) > "usr/bin/activate-remote"
    chmod +x "usr/bin/activate-remote"

    full_storepaths="$("${perl}/bin/perl" "${pathsFromGraph}" refs-*)"
    stripped_full_storepaths="$(echo "$full_storepaths" | sed -e 's|/*||')"

    # Reset timestamps to those of 'nix-store' to prevent annoying warnings.
    find usr -exec touch -h -r "${nix}/bin/nix-store" {} +

    # This is to be extracted on the other end using:
    #
    #   read -d: tarsize; head -c "$tarsize" | tar x; tar x
    #
    # The reason for the split is because I don't know of any method to
    # concatenate TAR archives from/to stdin/stdout without introducing new
    # dependencies.
    ( echo "#!${pkgsNative.stdenv.shell}"
      echo "lnum=\"\$(grep -m1 -an '^EXISTING_TAR${"\$"}' \"$installer\")\""
      echo 'scriptheadsize="$(head -n ''${lnum%%:*} "'"$installer"'" | wc -c)"'
      echo 'scriptsize="$(${pkgsNative.coreutils}/bin/stat -c %s "'"$installer"'")"'
      echo 'tarsize="$(($scriptsize - $scriptheadsize))"'
      echo 'echo -n "$tarsize:"'
      echo 'tail -n +$((''${lnum%%:*} + 1)) "'"$installer"'"'
      # As before, don't quote here!
      echo '${pkgsNative.gnutar}/bin/tar c -C /' $stripped_full_storepaths
      echo exit 0
      echo EXISTING_TAR
      tar c usr
    ) > "$installer"
    chmod +x "$installer"
  '';

  meta = {
    description = "Basic Nix bootstrap installer for NixOps";
    longDescription = ''
      It works like this:

      Prepare a base image with reference graph, which is to be copied over to
      the mount point and contains wrappers for the system outside the mount
      point. Those wrappers basically just chroot into the mountpoint path and
      execute the corresponding counterparts over there. The base derivation
      itself only contains everything necessary in order to get a Nix
      bootstrapped, like Nix itself and a shell linked to /mnt/bin/sh.

      From outside the mountpoint, we just provide a small script (hetzner-
      bootstrap) which contains a partitioner, activate-remote and a script
      which is the output of this derivation. In detail:

      hetzner-bootstrap: Creates a tarball of of the full closure of the base
                         derivation and its reference information, the
                         partitioner and activate-remote. The script outputs two
                         tarballs on stdout (the first one being prepended by
                         its size, like so: <size_first>:<first><second>) so
                         it's easy for NixOps to pipe it to the remote system.

      activate-remote: Copies the base derivation into /mnt and registers it
                       with the Nix database. Afterwards, it creates the
                       mentioned chroot wrappers and puts them into /usr/bin
                       (remember, we're on a non-NixOS system here), together
                       with the partitioner.
    '';
    platforms = stdenv.lib.platforms.all;
    maintainers = [ stdenv.lib.maintainers.aszlig ];
  };
}
