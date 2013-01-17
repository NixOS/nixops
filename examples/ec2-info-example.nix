{ config, pkgs, ... }:

with pkgs.lib;

{ deployment.ec2.accessKeyId = "AKIA...";
  deployment.ec2.keyPair = "...";
  deployment.ec2.privateKey = mkDefault "/home/eelco/.ssh/id_rsa-ec2-${config.deployment.ec2.region}";
  deployment.ec2.securityGroups = mkDefault [ "default" ];
}
