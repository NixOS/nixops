{ config, pkgs, ... }:

let

  clientKeyPath = "/root/.vbox-charon-client-key";

in

{ require = [ <nixos/modules/virtualisation/virtualbox-image.nix> ];

  services.openssh.enable = true;

  jobs."get-vbox-charon-client-key" =
    { description = "Get Charon SSH Key";
      wantedBy = [ "multi-user.target" ];
      before = [ "sshd.service" ];
      requires = [ "dev-vboxguest.device" ];
      after = [ "dev-vboxguest.device" ];
      path = [ config.boot.kernelPackages.virtualboxGuestAdditions ];
      preStart =
        ''
          set -o pipefail
          VBoxControl -nologo guestproperty get /VirtualBox/GuestInfo/Charon/ClientPublicKey | sed 's/Value: //' > ${clientKeyPath}.tmp
          mv ${clientKeyPath}.tmp ${clientKeyPath}
        '';
    };

  services.openssh.authorizedKeysFiles = [ ".vbox-charon-client-key" ];

  boot.vesa = false;

  boot.loader.grub.timeout = 1;

  # VirtualBox doesn't seem to lease IP addresses persistently, so we
  # may get a different IP address if dhcpcd is restarted.  So don't
  # restart dhcpcd.
  jobs.dhcpcd.restartIfChanged = false;
}
