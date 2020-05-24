{ pkgs, config, lib, ... }:

{
  imports = [
    <nixpkgs/nixos/modules/virtualisation/docker-image.nix>
    <nixpkgs/nixos/modules/installer/cd-dvd/channel.nix>
  ];

  users.extraUsers.root.openssh.authorizedKeys.keys = [
    (builtins.readFile ../snakeoil/id_ed25519.pub)
  ];

  services.openssh.enable = true;

  # We're not using the host resolver
  services.resolved.enable = true;
  networking.useHostResolvConf = false;
  networking.nameservers = [
    "1.1.1.1"
    "9.9.9.9"
  ];

  # These dont work nicely in containers
  # TODO: Upstream into nixos/modules/virtualisation/docker-image.nix
  services.nscd.enable = lib.mkForce false;
  system.nssModules = lib.mkForce [];
  networking.dhcpcd.enable = lib.mkForce false;

  services.journald.console = "/dev/console";

  systemd.services."serial-getty@ttyS0".enable = false;
  systemd.services."serial-getty@hvc0".enable = false;
  systemd.services."getty@tty1".enable = false;
  systemd.services."autovt@".enable = false;

  systemd.services.firewall.enable = false;
  systemd.services.systemd-resolved.enable = false;
  systemd.services.systemd-udevd.enable = false;

  security.sudo.wheelNeedsPassword = false;

  systemd.enableEmergencyMode = false;

  # We are using a local Nix daemon
  environment.variables.NIX_REMOTE = lib.mkForce "";

  # For some reason /etc/ssh gets the wrong permissions
  boot.postBootCommands = ''
    chown -R root:root /etc/ssh
  '';

  # security.audit.enable = lib.mkForce false;
  # is not sufficient as it's explicitly _disabled_ rather than just a no-op
  systemd.services.audit.serviceConfig = {
    ExecStart = lib.mkForce "${pkgs.coreutils}/bin/true";
    ExecStop = lib.mkForce "${pkgs.coreutils}/bin/true";
  };

  systemd.suppressedSystemUnits = [
    "sys-kernel-config.mount"
    "sys-kernel-debug.mount"
    "systemd-journald-audit.socket"
    "rescue.service"
    "rescue.target"
  ];

  environment.systemPackages = with pkgs; [
    bashInteractive
    cacert
    nix
  ];
}
