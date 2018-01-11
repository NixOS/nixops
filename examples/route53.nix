
{
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
    };

    mv2 = { resources, ... }: {
      zoneId = resources.route53HostedZones.hs;
      domainName = "mv.nixos.org.";
      ttl = 300;
      recordValues = [ "4.3.2.1" ];
      recordType = "A";
      setIdentifier = "id2";
      routingPolicy = "multivalue";
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
}
