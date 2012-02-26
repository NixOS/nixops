{ config, pkgs, ... }:

{ require = [ <nixos/modules/virtualisation/virtualbox-image.nix> ];

  services.openssh.enable = true;

  # For now, use a hard-coded key to access the VirtualBox VM.  Since
  # this is only for testing and they're not reachable from the
  # outside, this is not a big problem.
  users.extraUsers.root.openssh.authorizedKeys.keyFiles = [ ./id_charon-virtualbox.pub ];

  boot.vesa = false;
}
