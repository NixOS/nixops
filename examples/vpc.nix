{
  region ? "us-east-1"
, accessKeyId 
, ...
}:
with (import <nixpkgs> {}).lib;
{
  
  machine =
    {config, resources, pkgs, lib, ...}:
    {
      deployment.targetEnv = "ec2";
      deployment.ec2.accessKeyId = accessKeyId;
      deployment.ec2.associatePublicIpAddress = true;
      deployment.ec2.region = region;
      deployment.ec2.instanceType = "c3.large";
      deployment.ec2.subnetId = resources.vpcSubnets.subnet-b;
      deployment.ec2.keyPair = resources.ec2KeyPairs.keypair;
      deployment.ec2.securityGroups = [];
      deployment.ec2.securityGroupIds = [ resources.ec2SecurityGroups.sg.name ];
    };

  resources.ec2KeyPairs.keypair = { inherit region accessKeyId; };

  resources.ec2SecurityGroups = {
    sg =
      { resources, lib, ... }:
      {
        inherit region accessKeyId;
        vpcId = resources.vpc.vpc-nixops;
        rules = [
          { toPort = 22; fromPort = 22; sourceIp = "41.231.120.171/32"; }
        ];
      };
    };

  resources.vpc.vpc-nixops =
    {
      inherit region accessKeyId;
      instanceTenancy = "default";
      enableDnsSupport = true;
      enableDnsHostnames = true;
      cidrBlock = "10.0.0.0/16";
      tags = {
        Source = "NixOps";
      };
    };

  resources.vpcSubnets =
    let
      subnet = {cidr, zone}:
        { resources, ... }:
        {
          inherit region zone accessKeyId;
          vpcId = resources.vpc.vpc-nixops;
          cidrBlock = cidr;
          mapPublicIpOnLaunch = true;
          tags = {
            Source = "NixOps";
          };
        };
    in
    {
      subnet-a = subnet { cidr = "10.0.0.0/19"; zone = "us-east-1a"; };
      subnet-b = subnet { cidr = "10.0.32.0/19"; zone = "us-east-1b"; };
      subnet-c = subnet { cidr = "10.0.64.0/19"; zone = "us-east-1c"; };
      subnet-d = subnet { cidr = "10.0.96.0/19"; zone = "us-east-1d"; };
      subnet-e = subnet { cidr = "10.0.128.0/19"; zone = "us-east-1e"; };
      subnet-f = subnet { cidr = "10.0.160.0/19"; zone = "us-east-1f"; };
    };

  resources.vpcRouteTables =
  {
    route-table =
      { resources, ... }:
      {
        inherit region accessKeyId;
        vpcId = resources.vpc.vpc-nixops;
      };
  };

  resources.vpcRouteTableAssociations = 
    let
      subnets = ["subnet-a" "subnet-b" "subnet-c" "subnet-d" "subnet-e" "subnet-f"];
      association = subnet:
        { resources, ... }:
        {
          inherit region accessKeyId;
          subnetId = resources.vpcSubnets."${subnet}";
          routeTableId = resources.vpcRouteTables.route-table;
        };
    in
      (builtins.listToAttrs (map (s: nameValuePair "association-${s}" (association s) ) subnets));

  resources.vpcRoutes = {
    igw-route = 
      { resources, ... }:
      {
        inherit region accessKeyId;
        routeTableId = resources.vpcRouteTables.route-table;
        destinationCidrBlock = "0.0.0.0/0";
        gatewayId = resources.vpcInternetGateways.igw; 
      };
  };

  resources.elasticIPs.nat-eip =
    {
      inherit region accessKeyId;
      vpc = true;
    };

  resources.vpcNatGateways.nat =
    { resources, ... }:
    {
      inherit region accessKeyId;
      allocationId = resources.elasticIPs.nat-eip;
      subnetId = resources.vpcSubnets.subnet-f;
    };

  resources.vpcInternetGateways.igw = 
    { resources, ... }:
    {
      inherit region accessKeyId;
      vpcId = resources.vpc.vpc-nixops;
    };
}
