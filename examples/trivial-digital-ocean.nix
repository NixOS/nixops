{
  resources.sshKeyPairs.ssh-key = {};

  machine = { config, pkgs, ... }: {
    services.nginx.enable = true;
    services.openssh.enable = true;

    deployment.targetEnv = "digitalOcean";
    deployment.digitalOcean.enableIpv6 = true;
    deployment.digitalOcean.region = "ams2";
    deployment.digitalOcean.size = "512mb";
  };
}
