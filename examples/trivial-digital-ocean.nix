{
  machine = { config, pkgs, ... }: {

  environment.systemPackages = [ pkgs.git ];
  services.nginx.enable = true;

  # TODO the root fs stuff should move into
  imports = [ <nixpkgs/nixos/modules/profiles/qemu-guest.nix> ];
  boot.loader.grub.device = "/dev/vda";
  fileSystems."/" = { device = "/dev/vda1"; fsType = "ext4"; };

  networking.firewall.allowPing = true;
  services.openssh.enable = true;

  deployment.targetEnv = "digital-ocean";
  deployment.digital-ocean.region = "nyc3";
  deployment.digital-ocean.size = "512mb";
  deployment.digital-ocean.keyName = "teh";
  };
}
