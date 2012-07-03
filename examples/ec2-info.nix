{ config, pkgs, ... }:

with pkgs.lib;

{ deployment.ec2.accessKeyId = "AKIAIEMEJZVNOOHWZKZQ";
  deployment.ec2.keyPair = mkDefault "eelco";
  deployment.ec2.privateKey = mkDefault "/home/eelco/.ec2/logicblox/id_rsa-eelco-logicblox-${config.deployment.ec2.region}";
  deployment.ec2.securityGroups = mkDefault [ "eelco-test" ];
}
