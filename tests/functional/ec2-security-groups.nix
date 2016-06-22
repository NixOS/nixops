let
  region = "us-east-1";
in
{
  resources.ec2KeyPairs.my-key-pair =
    { inherit region; };

  resources.ec2SecurityGroups.ssh-security-group = {
    inherit region;
    description = "Security group for NixOps tests";
    rules = [ {
      fromPort = 22;
      toPort = 22;
      sourceIp = "0.0.0.0/0";
    } ];
  };

  resources.ec2SecurityGroups.can-access-server = {
    inherit region;
    name="can-access-server";
    rules = [ ];
  };

  resources.ec2SecurityGroups.server-access = {
    inherit region;
    rules = [ {
      fromPort = 80;
      toPort = 80;
      sourceGroup.groupName = "can-access-server";
    }];
  };

  server =
    { pkgs, resources, ... }:
    {
      deployment.targetEnv = "ec2";
      deployment.ec2 = {
        inherit region;
        instanceType = "c3.large";
        securityGroups = [
          resources.ec2SecurityGroups.ssh-security-group
          resources.ec2SecurityGroups.server-access
        ];
        keyPair = resources.ec2KeyPairs.my-key-pair;
      };

      networking.firewall.allowedTCPPorts = [ 80 ];

      services.httpd.enable = true;
      services.httpd.adminAddr = "alice@example.org";
      services.httpd.documentRoot = "${pkgs.valgrind.doc}/share/doc/valgrind/html";
    };

  client1 =
    { resources, ... }:
    {
      deployment.targetEnv = "ec2";
      deployment.ec2 = {
        inherit region;
        instanceType = "c3.large";
        securityGroups = [
          resources.ec2SecurityGroups.ssh-security-group
          resources.ec2SecurityGroups.can-access-server
        ];
        keyPair = resources.ec2KeyPairs.my-key-pair;
      };
    };

  client2 =
    { resources, ... }:
    {
      deployment.targetEnv = "ec2";
      deployment.ec2 = {
        inherit region;
        instanceType = "c3.large";
        securityGroups = [ resources.ec2SecurityGroups.ssh-security-group ];
        keyPair = resources.ec2KeyPairs.my-key-pair;
      };
    };
}
