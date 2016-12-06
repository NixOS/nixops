{
  resources.sshKeyPairs.ssh-key = {};

  machine = { config, pkgs, ... }: {
    services.nginx.enable = true;
    services.openssh.enable = true;

    deployment.targetEnv = "digital-ocean";
    deployment.digital-ocean.region = "ams2";
    deployment.digital-ocean.size = "512mb";
  };
}
