{ pkgs, diskImageFun }:

let
  plain = text: { inherit text; type = "plain"; };
  executable = text: { inherit text; type = "exec"; };

  fileMap = {
    backdoor = executable ''
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
    '';

    debian.install = plain ''
      backdoor usr/sbin
    '';

    debian.compat = plain "9";
    debian.source.format = plain "3.0 (native)";

    debian.changelog = plain ''
      backdoor (1-1) unstable; urgency=low

        * Dummy changelog for snakeoil key.

       -- Mr. Robot <evil@backdoor>  Thu, 01 Jan 1970 00:00:01 +0000
    '';

    debian.control = plain ''
      Source: backdoor
      Section: misc
      Priority: optional
      Maintainer: Mr. Robot <evil@backdoor>
      Build-Depends: debhelper (>= 9), dh-systemd
      Standards-Version: 3.9.6

      Package: backdoor
      Architecture: all
      Depends: ''${misc:Depends}
      Description: Backdoor For VM testing
    '';

    debian.rules = executable ''
      #!/usr/bin/make -f
      %:
      ${"\t"}dh $@ --with=systemd
    '';

    debian.service = plain ''
      [Unit]
      Description=Backdoor
      Requires=dev-hvc0.device
      Requires=dev-ttyS0.device
      After=dev-hvc0.device
      After=dev-ttyS0.device

      [Service]
      ExecStart=/usr/sbin/backdoor
      KillSignal=SIGHUP

      [Install]
      WantedBy=multi-user.target
    '';
  };

  genFile = path: name: { type ? null, text ? "", ... }@attrs: with pkgs.lib;
    if type == null
    then concatStrings (mapAttrsToList (genFile (path ++ [name])) attrs)
    else ''
      ${optionalString (path != []) ''
        mkdir -p "${concatStringsSep "/" path}"
      ''}
      cat > "${concatStringsSep "/" (path ++ [name])}" <<'EOF'
      ${text}
      EOF
      ${optionalString (type == "exec") ''
        chmod +x "${concatStringsSep "/" (path ++ [name])}"
      ''}
    '';

in pkgs.vmTools.runInLinuxImage (pkgs.stdenv.mkDerivation {
  name = "backdoor.deb";

  diskImage = diskImageFun {
    extraPackages = [ "build-essential" "debhelper" "dh-systemd" ];
  };

  buildCommand = ''
    mkdir backdoor
    cd backdoor
    ${with pkgs.lib; concatStrings (mapAttrsToList (genFile []) fileMap)}
    dpkg-buildpackage -b
    rmdir "$out" || :
    mv -vT ../*.deb "$out" # */
  '';
})
