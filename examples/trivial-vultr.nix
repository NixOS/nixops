{
  machine = { config, pkgs, ... }: {
    services.nginx.enable = true;
    services.openssh.enable = true;

    deployment.targetEnv = "vultr";
    deployment.vultr.snapshotid = "xxxxxxxxxxxxx";
    deployment.vultr.dcid = "1";
    deployment.vultr.vpsplanid = "201";
    deployment.vultr.label = "dev01.mydomain.com";
  };
}
