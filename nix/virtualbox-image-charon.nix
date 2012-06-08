{ config, pkgs, ... }:

let

  clientKeyPath = "/root/.vbox-client-key";

in

{ require = [ <nixos/modules/virtualisation/virtualbox-image.nix> ];

  services.openssh.enable = true;

  jobs."get-vbox-charon-client-key" =
    { startOn = "starting sshd";
      task = true;
      path = [ config.boot.kernelPackages.virtualboxGuestAdditions ];
      exec =
        ''
          VBoxControl -nologo guestproperty get /VirtualBox/GuestInfo/Charon/ClientPublicKey | sed 's/Value: //' > ${clientKeyPath}
        '';
    };

  users.extraUsers.root.openssh.authorizedKeys.keyFiles = [ clientKeyPath ];

  boot.vesa = false;

  # VirtualBox doesn't seem to lease IP addresses persistently, so we
  # may get a different IP address if dhcpcd is restarted.  So don't
  # restart dhcpcd.
  jobs.dhcpcd.restartIfChanged = false;
}
