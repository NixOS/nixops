{
  resources.sshKeyPairs.ssh-key = {};

  machine = { config, pkgs, ... }: {
    services.openssh.enable = true;

    deployment.targetEnv = "hetznerCloud";
    deployment.hetznerCloud.serverType = "cx11";

    networking.firewall.allowedTCPPorts = [ 22 ];
  };
}
