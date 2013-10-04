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
    environment.systemPackages = [ pkgs.nmap ];
  } // (if enableSecurityGroup then {
    deployment.ec2.securityGroups = [ resources.ec2SecurityGroups.test.name ];
  } else {});
}
