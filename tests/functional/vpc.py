from os import path
import tempfile

from nose import tools
from nose.plugins.attrib import attr
import boto3

from nixops.nix_expr import RawValue, Function, Call, py2nix
import nixops.util
from tests.functional import generic_deployment_test

parent_dir = path.dirname(__file__)

base_spec = "{}/vpc.nix".format(parent_dir)


class TestVPC(generic_deployment_test.GenericDeploymentTest):
    def setup(self):
        super(TestVPC, self).setup()
        self.depl.nix_exprs = [base_spec]
        self.exprs_dir = nixops.util.SelfDeletingDir(tempfile.mkdtemp("nixos-tests"))

    def test_deploy_vpc(self):
        self.depl.deploy()
        vpc_resource = self.depl.get_typed_resource("vpc-test", "vpc")
        vpc = vpc_resource.get_client().describe_vpcs(
            VpcIds=[vpc_resource._state["vpcId"]]
        )
        tools.ok_(len(vpc["Vpcs"]) > 0, "VPC not found!")
        tools.eq_(vpc["Vpcs"][0]["CidrBlock"], "10.0.0.0/16", "CIDR block mismatch")

    def test_deploy_vpc_machine(self):
        self.compose_expressions([CFG_SUBNET, CFG_INTERNET_ROUTE, CFG_VPC_MACHINE])
        self.depl.deploy(plan_only=True)
        self.depl.deploy()

    def test_enable_dns_support(self):
        self.compose_expressions([CFG_DNS_SUPPORT])
        self.depl.deploy(plan_only=True)
        self.depl.deploy()

    def test_enable_ipv6(self):
        self.compose_expressions([CFG_IPV6])
        self.depl.deploy(plan_only=True)
        self.depl.deploy()
        vpc_resource = self.depl.get_typed_resource("vpc-test", "vpc")
        vpc = vpc_resource.get_client().describe_vpcs(
            VpcIds=[vpc_resource._state["vpcId"]]
        )
        ipv6_block = vpc["Vpcs"][0]["Ipv6CidrBlockAssociationSet"]
        tools.ok_(len(ipv6_block) > 0, "There is no Ipv6 block")
        tools.ok_(
            ipv6_block[0].get("Ipv6CidrBlock", None) != None,
            "No Ipv6 cidr block in the response",
        )

    def test_deploy_subnets(self):
        # FIXME might need to factor out resources into separate test
        # classes depending on the number of tests needed.
        self.compose_expressions([CFG_SUBNET])
        self.depl.deploy(plan_only=True)
        self.depl.deploy()
        subnet_resource = self.depl.get_typed_resource("subnet-test", "vpc-subnet")
        subnet = subnet_resource.get_client().describe_subnets(
            SubnetIds=[subnet_resource._state["subnetId"]]
        )
        tools.ok_(len(subnet["Subnets"]) > 0, "VPC subnet not found!")

    def test_deploy_nat_gtw(self):
        self.compose_expressions([CFG_SUBNET, CFG_NAT_GTW])
        self.depl.deploy(plan_only=True)
        self.depl.deploy()

    def compose_expressions(self, configurations):
        extra_exprs = list(map(self.generate_config, configurations))
        self.depl.nix_exprs = [base_spec] + extra_exprs

    def generate_config(self, config):
        basename, expr = config
        expr_path = "{0}/{1}".format(self.exprs_dir, basename)
        with open(expr_path, "w") as cfg:
            cfg.write(expr)
        return expr_path


CFG_VPC_MACHINE = (
    "network.nix",
    """
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
  """,
)

CFG_INTERNET_ROUTE = (
    "igw_route.nix",
    """
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
  """,
)

CFG_DNS_SUPPORT = (
    "enable_dns_support.nix",
    py2nix({("resources", "vpc", "vpc-test", "enableDnsSupport"): True}),
)

CFG_IPV6 = (
    "ipv6.nix",
    py2nix({("resources", "vpc", "vpc-test", "amazonProvidedIpv6CidrBlock"): True}),
)

CFG_NAT_GTW = (
    "nat_gtw.nix",
    """
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
    """,
)

CFG_SUBNET = (
    "subnet.nix",
    """
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
    """,
)
