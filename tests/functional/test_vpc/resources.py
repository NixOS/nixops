from nixops.nix_expr import py2nix

CFG_VPC_MACHINE = ("network.nix", """
  {
      machine =
        {config, resources, pkgs, lib, ...}:
        {
          deployment.targetEnv = "ec2";
          deployment.hasFastConnection = true;
          deployment.ec2.associatePublicIpAddress = true;
          deployment.ec2.region = "us-east-1";
          deployment.ec2.instanceType = "c3.large";
          deployment.ec2.subnetId = resources.vpcSubnets.subnet-test;
          deployment.ec2.keyPair = resources.ec2KeyPairs.keypair.name;
          deployment.ec2.securityGroups = [];
          deployment.ec2.securityGroupIds = [ resources.ec2SecurityGroups.public-ssh.name ];
        };

      resources.ec2KeyPairs.keypair = { region = "us-east-1"; };
      resources.ec2SecurityGroups.public-ssh =
        { resources, ... }:
        {
          region = "us-east-1";
          vpcId = resources.vpc.vpc-test;
          rules = [{ toPort = 22; fromPort = 22; sourceIp = "0.0.0.0/0"; }];
        };
  }
  """)

CFG_INTERNET_ROUTE = ("igw_route.nix", """
  let
    region = "us-east-1";
  in
  {
    resources = {

      vpcRouteTables.route-table =
        { resources, ... }:
        { inherit region; vpcId = resources.vpc.vpc-test; };

      vpcRouteTableAssociations.association-test =
        { resources, ... }:
        {
          inherit region;
          subnetId = resources.vpcSubnets.subnet-test;
          routeTableId = resources.vpcRouteTables.route-table;
        };

      vpcRoutes.igw-route =
        { resources, ... }:
        {
          inherit region;
          routeTableId = resources.vpcRouteTables.route-table;
          destinationCidrBlock = "0.0.0.0/0";
          gatewayId = resources.vpcInternetGateways.igw-test;
        };

      vpcInternetGateways.igw-test =
        { resources, ... }:
        {
          inherit region;
          vpcId = resources.vpc.vpc-test;
        };
    };
  }
  """)

CFG_DNS_SUPPORT = ("enable_dns_support.nix", py2nix({
    ('resources', 'vpc', 'vpc-test', 'enableDnsSupport'): True
}))

CFG_IPV6 = ("ipv6.nix", py2nix({
    ('resources', 'vpc', 'vpc-test', 'amazonProvidedIpv6CidrBlock'): True
}))

CFG_NAT_GTW = ("nat_gtw.nix", """
   {
      resources.elasticIPs.nat-eip =
      {
        region = "us-east-1";
        vpc = true;
      };

      resources.vpcNatGateways.nat =
        { resources, ... }:
        {
          region = "us-east-1";
          allocationId = resources.elasticIPs.nat-eip;
          subnetId = resources.vpcSubnets.subnet-test;
        };
    }
    """)

CFG_SUBNET = ("subnet.nix", """
    {
      resources.vpcSubnets.subnet-test =
        { resources, ... }:
        {
          region = "us-east-1";
          zone = "us-east-1a";
          vpcId = resources.vpc.vpc-test;
          cidrBlock = "10.0.0.0/19";
          mapPublicIpOnLaunch = true;
          tags = {
            Source = "NixOps Tests";
          };
        };
    }
    """)
