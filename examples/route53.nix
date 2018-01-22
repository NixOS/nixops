
{
  machine =
    { resources, ... }:
    { imports = [ ./ec2-info.nix ./nix-homepage.nix ];
      deployment.targetEnv = "ec2";
      deployment.ec2.region = "us-east-1";
      deployment.ec2.instanceType = "r3.large";
      deployment.ec2.securityGroups = [ resources.ec2SecurityGroups.ssh-security-group ];
    };

  resources.ec2SecurityGroups.ssh-security-group = {
     region = "us-east-1";
     rules = [ {
       fromPort = 22;
       toPort = 22;
       sourceIp = "0.0.0.0/0";
     } {
       fromPort = 80;
       toPort = 80;
       sourceIp = "0.0.0.0/0";
     }];
   };

  resources.route53HostedZones.hs =
      { name = "nixos.org.";
        comment = "Hosted zone for nixos.org";
      };

  resources.route53RecordSets = {

    a-record = { resources, ... }: {
      zoneId = resources.route53HostedZones.hs;
      domainName = "www.nixos.org.";
      ttl = 300;
      recordValues = [ "1.2.3.4" ];
      recordType = "A";
    };

    mv1 = { resources, ... }: {
      zoneId = resources.route53HostedZones.hs;
      domainName = "mv.nixos.org.";
      recordValues = [ "1.2.3.4" ];
      recordType = "A";
      setIdentifier = "id1";
      routingPolicy = "multivalue";
      healthCheckId = resources.route53HealthChecks.my-google-check;
    };

    mv2 = { resources, ... }: {
      zoneId = resources.route53HostedZones.hs;
      domainName = "mv.nixos.org.";
      ttl = 300;
      recordValues = [ "4.3.2.1" ];
      recordType = "A";
      setIdentifier = "id2";
      routingPolicy = "multivalue";
      healthCheckId = resources.route53HealthChecks.my-machine-check;
    };

    weight1 = { resources, ... }: {
      zoneId = resources.route53HostedZones.hs;
      domainName = "weight.nixos.org.";
      weight = 10;
      recordValues = [ "5.4.3.2" ];
      recordType = "A";
      setIdentifier = "id1";
      routingPolicy = "weighted";
    };

    weight2 = { resources, ... }: {
      zoneId = resources.route53HostedZones.hs;
      domainName = "weight.nixos.org.";
      weight = 20;
      recordValues = [ "2.3.4.5" ];
      recordType = "A";
      setIdentifier = "id2";
      routingPolicy = "weighted";
    };
  };

  resources.route53HealthChecks = {
    my-google-check = {
      type = "HTTPS";
      fullyQualifiedDomainName = "www.google.com";
    };
    my-machine-check = { resources, ... }: {
      type = "HTTP";
      ipAddress = resources.machines.machine;
    };
    my-machine-check-with-resource-path = { resources, ... }: {
      type = "HTTP";
      ipAddress = resources.machines.machine;
      resourcePath = "/nixops/";
    };
    calc-check = { resources, ... }: {
      type = "CALCULATED";
      childHealthChecks = [
        resources.route53HealthChecks.my-google-check
        resources.route53HealthChecks.my-machine-check
      ];
    };
  };
}
