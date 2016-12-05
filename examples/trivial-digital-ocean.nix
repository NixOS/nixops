{
  machine = { config, pkgs, ... }: {

  environment.systemPackages = [ pkgs.git ];
  services.nginx.enable = true;

  networking.useDHCP = true;
  networking.firewall.allowPing = true;
  networking.firewall.enable = false;
  services.openssh.enable = true;

  security.grsecurity.enable = true;

  deployment.targetEnv = "digital-ocean";
  deployment.digital-ocean.region = "ams2";
  deployment.digital-ocean.size = "512mb";
  deployment.digital-ocean.keyName = "teh";
  };
}
