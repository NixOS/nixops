{ openPort, enableSecurityGroup, ... }:
{
  resources.ec2SecurityGroups.test = {
    region = "us-east-1";
    rules = if openPort then [ {
      fromPort = 3030;
      toPort = 3030;
      sourceIp = "0.0.0.0/0";
    } ] else [];
  };

  machine = { pkgs, resources, ... }: {
    systemd.services.ncat = {
      description = "Listen on 3030";
      serviceConfig.ExecStart = "@${pkgs.nmap}/bin/ncat ncat -kl -p 3030";
    };
    environment.systemPackages = [ pkgs.nmap ];
  } // (if enableSecurityGroup then {
    deployment.ec2.securityGroups = [ resources.ec2SecurityGroups.test.name ];
  } else {});
}
